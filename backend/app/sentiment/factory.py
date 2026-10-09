"""Sentiment analyzer factory driven by client settings (T9).

``local``  -> LayaAnalyzer (lazy; the model loads on first analyze).
``openai`` -> ApiSentimentAnalyzer against the configured OpenAI-compatible
endpoint, with the local analyzer chained as runtime fallback when
``fallback_local`` is set (ai_fallback_local). An openai selection without
an API key degrades to local with a warning instead of failing the cycle.
"""

import logging

from app.sentiment.api_analyzer import ApiSentimentAnalyzer
from app.sentiment.base import SentimentAnalyzer
from app.sentiment.laya_analyzer import LayaAnalyzer

log = logging.getLogger("sentiment.factory")


def build_sentiment_analyzer(
    *,
    provider: str = "local",
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
    fallback_local: bool = True,
) -> SentimentAnalyzer:
    """Build the analyzer for one ingest cycle (cached per cycle upstream)."""
    normalized = (provider or "local").strip().lower()
    if normalized != "openai":
        return LayaAnalyzer()
    if not api_key:
        log.warning("ai provider 'openai' configured without api_key; using local analyzer")
        return LayaAnalyzer()
    fallback: SentimentAnalyzer | None = LayaAnalyzer() if fallback_local else None
    return ApiSentimentAnalyzer(
        api_key=api_key,
        base_url=base_url,
        model=model,
        fallback=fallback,
    )
