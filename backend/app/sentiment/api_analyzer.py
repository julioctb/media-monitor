"""OpenAI-compatible chat-completions sentiment analyzer (T9).

POSTs {base_url}/chat/completions with the configured model and key; the
prompt demands exactly one word (positive|neutral|negative). The score is
a fixed value per label on the bipolar scale the enrichment writer
defines (0 = negative, 0.5 = neutral, 1 = positive). Transport: httpx,
20s timeout, 3 attempts.

Roles: the worker builds it as the sentiment FALLBACK for rows whose
enrichment failed; the settings probe instantiates it directly as a
connectivity check.
"""

import logging
import re
import time

import httpx

from app.models.base import Sentiment
from app.sentiment.base import SentimentAnalyzer, SentimentResult

log = logging.getLogger("sentiment.api")

DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
#: Fixed per-label scores on the bipolar sentiment_score column (0.5 =
#: neutral, <0.5 negative, >0.5 positive) — the semantics the enrichment
#: writer already stores; a label confidence was never a position on it.
LABEL_SCORES: dict[Sentiment, float] = {
    Sentiment.negative: 0.4,
    Sentiment.neutral: 0.5,
    Sentiment.positive: 0.8,
}
TIMEOUT_S = 20.0
ATTEMPTS = 3
BACKOFF_S = 0.5

_PROMPT = (
    "Classify the sentiment towards the protagonist of the text (the "
    "subject of the headline), not the event itself. "
    "Answer with exactly one word: positive, neutral or negative."
)

_LABEL_RE = re.compile(r"\b(positive|neutral|negative)\b", re.IGNORECASE)


def parse_label(content: str) -> Sentiment:
    """First positive/neutral/negative word in the completion body."""
    match = _LABEL_RE.search(content or "")
    if match is None:
        raise ValueError(f"unexpected sentiment completion: {content!r}")
    return Sentiment(match.group(1).lower())


class ApiSentimentAnalyzer(SentimentAnalyzer):
    """Sentiment via an OpenAI-compatible chat completions endpoint."""

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
        return SentimentResult(label=label, score=LABEL_SCORES[label])

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
        assert last_error is not None  # at least one attempt always ran
        raise last_error

    def close(self) -> None:
        if self._owns_client:
            self._client.close()
