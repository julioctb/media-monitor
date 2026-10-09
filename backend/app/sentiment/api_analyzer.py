"""OpenAI-compatible chat-completions sentiment analyzer (T9).

POSTs {base_url}/chat/completions with the configured model and key; the
prompt demands exactly one word (positive|neutral|negative). The score is
the chosen label's logprob when the response carries logprobs, else the
flat 0.8 default. Transport: httpx, 20s timeout, 3 attempts.

``fallback`` (typically the local Laya analyzer, per ai_fallback_local)
chains in when every attempt fails, so a dead API never stalls ingest.
"""

import logging
import math
import re
import time

import httpx

from app.models.base import Sentiment
from app.sentiment.base import SentimentAnalyzer, SentimentResult

log = logging.getLogger("sentiment.api")

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
DEFAULT_SCORE = 0.8
TIMEOUT_S = 20.0
ATTEMPTS = 3
BACKOFF_S = 0.5

_PROMPT = (
    "Classify the sentiment towards the brand or subject named in the text. "
    "Judge the subject, not the event itself. "
    "Answer with exactly one word: positive, neutral or negative."
)

_LABEL_RE = re.compile(r"\b(positive|neutral|negative)\b", re.IGNORECASE)


def parse_label(content: str) -> Sentiment:
    """First positive/neutral/negative word in the completion body."""
    match = _LABEL_RE.search(content or "")
    if match is None:
        raise ValueError(f"unexpected sentiment completion: {content!r}")
    return Sentiment(match.group(1).lower())


def _score_from(payload: dict, label: Sentiment) -> float:
    """exp(logprob) of the label token when logprobs came back, else 0.8."""
    try:
        parts = payload["choices"][0].get("logprobs") or {}
        for item in parts.get("content") or []:
            token = str(item.get("token") or "")
            logprob = item.get("logprob")
            if label.value in token.lower() and isinstance(logprob, (int, float)):
                return min(1.0, max(0.0, math.exp(logprob)))
    except (KeyError, IndexError, TypeError):  # shape varies across servers
        pass
    return DEFAULT_SCORE


class ApiSentimentAnalyzer(SentimentAnalyzer):
    """Sentiment via an OpenAI-compatible chat completions endpoint."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None = None,
        model: str | None = None,
        fallback: SentimentAnalyzer | None = None,
        client: httpx.Client | None = None,
        timeout: float = TIMEOUT_S,
        attempts: int = ATTEMPTS,
        backoff_s: float = BACKOFF_S,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required for the openai provider")
        self._api_key = api_key
        self._base_url = (base_url or DEFAULT_OPENAI_BASE_URL).rstrip("/")
        self._model = model or DEFAULT_OPENAI_MODEL
        self._fallback = fallback
        self._client = client or httpx.Client(timeout=timeout)
        self._owns_client = client is None
        self._attempts = max(1, attempts)
        self._backoff_s = backoff_s

    @property
    def model_name(self) -> str:
        return self._model

    def completions_url(self) -> str:
        return f"{self._base_url}/chat/completions"

    def _request(self, text: str) -> SentimentResult:
        resp = self._client.post(
            self.completions_url(),
            json={
                "model": self._model,
                "messages": [
                    {"role": "system", "content": _PROMPT},
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
            },
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        payload = resp.json()
        choice = payload["choices"][0]
        label = parse_label(choice["message"]["content"])
        return SentimentResult(label=label, score=_score_from(payload, label))

    def analyze(self, text: str, lang: str) -> SentimentResult:
        last_error: Exception | None = None
        for attempt in range(self._attempts):
            if attempt:
                time.sleep(self._backoff_s * attempt)
            try:
                return self._request(text)
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
                last_error = exc
                log.debug(
                    "sentiment api attempt %d/%d failed: %s", attempt + 1, self._attempts, exc
                )
        if self._fallback is not None:
            log.warning("sentiment api failed after %d attempts (%s); local fallback", self._attempts, last_error)
            return self._fallback.analyze(text, lang)
        assert last_error is not None  # at least one attempt always ran
        raise last_error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
