"""LLM mention enrichment: one structured pass per mention (F2c TE1).

A single chat-completions call per mention yields everything the rest of
the pipeline consumes (F2 plan: un llamado, muchos campos — the per-feature
alternative multiplies cost and latency x4):

  - summary (<= 2 lines, Spanish, no invention)
  - sentiment + sentiment_score, anchored to the SUBJECT of the piece
    (the laya v5 anchoring rules, kept verbatim in the prompt)
  - persons [{name, role, org, statement, stance}] — absorbs the future F3
    extractor; F2c carries the data, F3 persists it
  - topics (multi-label, stored through the existing classifications)

Transport mirrors app.sentiment.api_analyzer: OpenAI-compatible chat
completions, Bearer key, temperature 0, JSON mode, article truncated to
MAX_CONTENT_CHARS. Every failure mode (transport, shape, broken JSON,
schema violation) returns None after the retries — the caller falls back
to plain sentiment (laya) and the row stays backfillable.

``agreement_analyzer`` (TE5): when set, the agreement is logged alongside
each successful enrichment — but only when that analyzer has actually run
(``loaded``); the check never triggers a lazy load by itself.
"""

import json
import logging
import re
import time

import httpx
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.base import Sentiment

log = logging.getLogger("enrich.llm")

# Keep in sync with app.sentiment.api_analyzer / app.models.settings.
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
TIMEOUT_S = 20.0
ATTEMPTS = 2
BACKOFF_S = 0.5

#: Article text handed to the model, truncated (plan: ~1500 chars).
MAX_CONTENT_CHARS = 1500

#: Flat output-token estimate per enrichment, for the TE4 cost projection.
ESTIMATED_OUTPUT_TOKENS = 300

SYSTEM_PROMPT = (
    "Eres el extractor estructural de un monitor de medios. Analiza la nota "
    "y responde EXCLUSIVAMENTE con un objeto JSON valido con exactamente "
    'estas claves: {"summary": str, "sentiment": "positive"|"neutral"|'
    '"negative", "sentiment_score": float, "persons": lista, "topics": lista}. '
    "Reglas: "
    "summary: maximo 2 lineas en espanol, fiel al texto, sin inventar datos. "
    "sentiment/sentiment_score: valora la postura hacia la persona o marca "
    "PROTAGONISTA del texto (el sujeto del titular), no la gravedad del hecho "
    "ni el animo general; score entre 0 y 1. "
    "persons: personas nombradas en el texto, cada una "
    '{"name": str, "role": str|null, "org": str|null, "statement": str|null, '
    '"stance": str|null}; statement es cita textual solo si la nota la trae; '
    "stance es la postura que la persona expresa, null si no expresa ninguna. "
    "topics: entre 1 y 3 temas cortos en minusculas."
)


class EnrichedPerson(BaseModel):
    """One person named by the enrichment pass (F3 persists these)."""

    model_config = ConfigDict(strict=True, extra="ignore")

    name: str
    role: str | None = None
    org: str | None = None
    statement: str | None = None
    stance: str | None = None


class EnrichmentResult(BaseModel):
    """Strict schema of one LLM enrichment pass."""

    model_config = ConfigDict(strict=True, extra="ignore")

    summary: str
    sentiment: Sentiment
    sentiment_score: float = Field(ge=0.0, le=1.0)
    persons: list[EnrichedPerson] = []
    topics: list[str] = []

    @field_validator("summary", mode="before")
    @classmethod
    def _clean_summary(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary must not be empty")
        return cleaned

    @field_validator("sentiment", mode="before")
    @classmethod
    def _coerce_sentiment(cls, value: object) -> object:
        if isinstance(value, str):
            return Sentiment(value.strip().lower())
        return value

    @field_validator("sentiment_score", mode="before")
    @classmethod
    def _coerce_score(cls, value: object) -> object:
        if isinstance(value, str):
            return float(value)
        return value

    @field_validator("persons", mode="before")
    @classmethod
    def _clean_persons(cls, value: object) -> object:
        """Drop nameless persons; models emit name:null fillers often."""
        if not isinstance(value, list):
            return value
        cleaned = []
        for item in value:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            person = dict(item)
            person["name"] = name.strip()
            cleaned.append(person)
        return cleaned

    @field_validator("topics", mode="before")
    @classmethod
    def _clean_topics(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [topic.strip() for topic in value if isinstance(topic, str) and topic.strip()]


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def parse_enrichment(content: str) -> EnrichmentResult:
    """Parse one completion body into an EnrichmentResult.

    Raises ValueError on anything that is not a schema-valid JSON object
    (the retry loop upstream turns that into a fallback).
    """
    try:
        data = json.loads(_strip_code_fence(content))
    except json.JSONDecodeError as exc:
        raise ValueError(f"enrichment payload is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("enrichment payload must be a JSON object")
    return EnrichmentResult.model_validate(data)


class LLMEnricher:
    """Structured enrichment via an OpenAI-compatible endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        client: httpx.Client | None = None,
        timeout: float = TIMEOUT_S,
        attempts: int = ATTEMPTS,
        backoff_s: float = BACKOFF_S,
        agreement_analyzer=None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for the openai provider")
        self._api_key = api_key
        self._base_url = (base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self._model = model or DEFAULT_OPENAI_MODEL
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._attempts = max(1, attempts)
        self._backoff_s = backoff_s
        self._agreement = agreement_analyzer

    @property
    def model_name(self) -> str:
        return self._model

    def completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _chat(self, system: str, user: str, *, json_mode: bool) -> str:
        """One attempt; raises on transport/shape errors."""
        payload: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        resp = self._client.post(
            self.completions_url(),
            json=payload,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        return str(resp.json()["choices"][0]["message"]["content"])

    def _with_retries(self, fn):  # type: ignore[no-untyped-def]
        """Run fn() with the attempt/backoff policy; None once exhausted."""
        last_error: Exception | None = None
        for attempt in range(self._attempts):
            if attempt:
                time.sleep(self._backoff_s * attempt)
            try:
                return fn()
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                last_error = exc
                log.debug("enrich attempt %d/%d failed: %s", attempt + 1, self._attempts, exc)
        log.warning("enrichment failed after %d attempts (%s)", self._attempts, last_error)
        return None

    def enrich(self, text: str, lang: str = "es") -> EnrichmentResult | None:
        """One structured pass; None when the LLM path fails entirely."""
        del lang  # prompt and rules are Spanish-only for now
        article = " ".join((text or "").split())[:MAX_CONTENT_CHARS]
        if not article:
            return None

        def call() -> EnrichmentResult:
            content = self._chat(SYSTEM_PROMPT, article, json_mode=True)
            return parse_enrichment(content)  # bad JSON retried like a 500

        result = self._with_retries(call)
        if result is None:
            return None
        self._log_agreement(text, result)
        return result

    def _log_agreement(self, text: str, result: EnrichmentResult) -> None:
        """TE5: local-vs-LLM sentiment agreement, one week of data.

        Fires only when the agreement analyzer has actually run (its
        ``loaded`` flag is true); the check never triggers a load — a
        cycle whose sentiment stayed on the API path logs nothing.
        """
        if self._agreement is None:
            return
        if getattr(self._agreement, "loaded", True) is False:
            return
        try:
            local = self._agreement.analyze(text, "es")
        except Exception as exc:  # noqa: BLE001 - telemetry must not break ingest
            log.debug("agreement analyzer failed: %s", exc)
            return
        log.info(
            "enrich-agreement enrich=%s/%.2f laya=%s/%.2f match=%s",
            result.sentiment.value,
            result.sentiment_score,
            local.label.value,
            local.score,
            local.label is result.sentiment,
        )

    def summarize(self, inputs: list[str]) -> str | None:
        """Event summary from >=2 mention summaries; None on failure."""
        bullets = "\n".join(f"- {item.strip()[:300]}" for item in inputs if item.strip())
        system = (
            "Redacta un unico parrafo de 2 a 3 lineas que resuma el "
            "acontecimiento compartido por las notas. Usa solo la informacion "
            "dada, en espanol, sin inventar datos. Responde solo con el parrafo."
        )
        user = f"Notas del mismo acontecimiento:\n{bullets}"
        content = self._with_retries(
            lambda: self._chat(system, user, json_mode=False)
        )
        if content is None:
            return None
        return content.strip() or None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> "LLMEnricher":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
