"""Sentiment analyzer factory driven by client settings (T9).

``local``  -> the shared lazy Laya analyzer (the model loads on first
``analyze`` — see ``app.sentiment.laya_analyzer.LayaRuntime``).
``openai`` -> ApiSentimentAnalyzer against the configured OpenAI-compatible
endpoint, with the local analyzer chained as runtime fallback when
``fallback_local`` is set (ai_fallback_local). An openai selection without
an API key degrades to local with a warning instead of failing the cycle.

Lazy-optional (TE-lazy): nothing Laya-shaped is built per cycle. Both the
primary local analyzer and the API fallback are the process-wide
``shared_laya()`` proxy, which imports and constructs ``LayaAnalyzer`` —
and with it loads the model — only on the first actual ``analyze`` call.
A cycle backed by the API provider therefore never touches Laya unless a
fallback (API failure, or enrichment failure with no usable provider) fires.
"""

import logging
import threading

from app.sentiment.api_analyzer import ApiSentimentAnalyzer
from app.sentiment.base import SentimentAnalyzer, SentimentResult

log = logging.getLogger("sentiment.factory")


class LazyLayaAnalyzer(SentimentAnalyzer):
    """Defers the LayaAnalyzer construction until the first analyze().

    Constructing ``LayaAnalyzer`` is cheap, but keeping the construction
    behind this proxy makes "laya never ran" observable (``loaded``) and
    lets the whole process share one instance — the enrich-agreement
    telemetry checks ``loaded`` to log only when laya actually ran.
    """

    def __init__(self) -> None:
        self._inner: SentimentAnalyzer | None = None
        self._lock = threading.Lock()

    @property
    def loaded(self) -> bool:
        return self._inner is not None

    def _materialize(self) -> SentimentAnalyzer:
        if self._inner is None:
            with self._lock:
                if self._inner is None:
                    # Imported here so the module import itself stays
                    # optional; the model load inside stays lazy as before.
                    from app.sentiment.laya_analyzer import LayaAnalyzer

                    log.info("laya analyzer materialized on first need")
                    self._inner = LayaAnalyzer()
        return self._inner

    def analyze(self, text: str, lang: str) -> SentimentResult:
        return self._materialize().analyze(text, lang)


_laya_singleton: LazyLayaAnalyzer | None = None
_laya_singleton_lock = threading.Lock()


def shared_laya() -> LazyLayaAnalyzer:
    """Process-wide lazy laya analyzer: one proxy, one model load, ever.

    The sentiment fallback and the enrich-agreement analyzer deliberately
    share this instance, so agreement telemetry reflects whether the
    sentiment path ever materialized laya in this process.
    """
    global _laya_singleton
    if _laya_singleton is None:
        with _laya_singleton_lock:
            if _laya_singleton is None:
                _laya_singleton = LazyLayaAnalyzer()
    return _laya_singleton


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
        return shared_laya()
    if not api_key:
        log.warning("ai provider 'openai' configured without api_key; using local analyzer")
        return shared_laya()
    fallback: SentimentAnalyzer | None = shared_laya() if fallback_local else None
    return ApiSentimentAnalyzer(
        api_key=api_key,
        base_url=base_url,
        model=model,
        fallback=fallback,
    )
