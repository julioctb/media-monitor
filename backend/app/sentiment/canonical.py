"""Canonical sentiment policy: enrichment (raw_enrichment) is the truth.

The LLM enrichment verdict decides ``mentions.sentiment`` /
``sentiment_score`` whenever it carries a sentiment; the API analyzer
only fills rows that have no enrichment. When the canonical write
replaces a previously stored value, the old value (label + score) is
logged, so the pre-override value stays recoverable from the logs
without a schema change.
"""

import logging

from app.models.base import Sentiment

log = logging.getLogger("sentiment.canonical")


def apply_canonical_sentiment(
    subject,
    sentiment: Sentiment | None,
    sentiment_score: float | None,
    *,
    mention_id: int | None = None,
) -> bool:
    """Write the canonical sentiment onto ``subject``; True when changed.

    Idempotent: an equal label/score pair is a no-op. A differing
    previous value is preserved by logging it before the overwrite.
    ``sentiment is None`` writes nothing (the row stays backfillable).
    """
    if sentiment is None:
        return False
    previous_label = getattr(subject, "sentiment", None)
    previous_score = getattr(subject, "sentiment_score", None)
    changed = previous_label != sentiment or previous_score != sentiment_score
    if not changed:
        return False
    if previous_label is not None and previous_label != sentiment:
        log.info(
            "canonical sentiment override mention=%s: %s(%s) -> %s(%s)",
            mention_id if mention_id is not None else getattr(subject, "id", "?"),
            _label(previous_label),
            previous_score,
            _label(sentiment),
            sentiment_score,
        )
    subject.sentiment = sentiment
    subject.sentiment_score = sentiment_score
    return True


def _label(value: object) -> str:
    return value.value if isinstance(value, Sentiment) else str(value)
