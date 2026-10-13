"""Ingest pipeline: adapter output -> keyword match -> dedupe -> insert.

One function (`run_ingest_cycle`) drives every adapter for one client's
active keywords, re-validates the keyword match on the item text (accent-
and case-insensitive), scores sentiment, and inserts mentions through
queries.insert_mention so url_hash dedupe and client scoping are enforced
in exactly one place.
"""

import logging
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.classifications.base import Classifier, classification_results
from app.ingest.base import RawMention, SourceAdapter
from app.ingest.matching import find_matching_keyword, fold_text
from app.models import Keyword, MentionSource, queries
from app.models.base import Sentiment

log = logging.getLogger("ingest.pipeline")


def _text_of(item: RawMention) -> str:
    parts = [item.title or "", item.content or ""]
    return "\n".join(p for p in parts if p)


def _classify_mention(
    session: Session,
    *,
    mention_id: int,
    text: str,
    lang: str,
    classifiers: Sequence[Classifier],
) -> int:
    """Run every classifier over the text; store what succeeds.

    A classifier failure only skips its own rows (mention stays insertable
    and the remaining classifiers still run); rows land only via commit.
    Returns the number of classifiers that produced a row.
    """
    if not text.strip():
        return 0
    stored = 0
    for classifier in classifiers:
        try:
            result = classifier.classify(text, lang=lang)
        except Exception as exc:  # noqa: BLE001 - one classifier must not block the rest
            log.warning(
                "classifier %s failed for mention %s: %s", classifier.name, mention_id, exc
            )
            continue
        results = classification_results(result)
        # Multi-label classifiers land one row per label; an empty result
        # just clears the classifier's previous rows for this mention.
        queries.upsert_classifications(
            session,
            mention_id=mention_id,
            classifier=classifier.name,
            results=[(item.label, item.score) for item in results],
        )
        if results:
            stored += 1
    if stored:
        session.commit()
    return stored


def persist_raw_mentions(
    session: Session,
    *,
    client_id: int,
    items: list[RawMention],
    keyword_by_text: Mapping[str, Keyword],
    all_keyword_texts: list[str],
    sentiment_analyzer=None,
    classifiers: Sequence[Classifier] | None = None,
) -> int:
    """Validate, score and insert raw mentions; returns inserted count.

    - Re-checks the keyword match on title+content (fetch-time match from
      the source is advisory; the regex engine is the source of truth).
    - Falls back to any other tracked keyword if the fetch keyword does not
      literally appear in the text (sources rewrite titles).
    - Sentiment is scored once per inserted mention when an analyzer is
      provided; failures never block the insert (sentiment stays NULL and
      can be backfilled).
    - Registry classifiers run after sentiment, same failure isolation:
      a broken classifier leaves no rows instead of dropping the mention.
    """
    inserted = 0
    active_texts = set(all_keyword_texts)
    for item in items:
        text = _text_of(item)
        # Prefer the keyword that surfaced the item, but only if it is an
        # ACTIVE tracked keyword; otherwise fall back to any active keyword.
        preferred = [item.keyword] if item.keyword in active_texts else []
        matched_text = find_matching_keyword(text, preferred)
        if matched_text is None:
            matched_text = find_matching_keyword(text, all_keyword_texts)
        if matched_text is None:
            continue

        keyword = keyword_by_text.get(fold_text(matched_text))
        sentiment: Sentiment | None = None
        sentiment_score: float | None = None
        if sentiment_analyzer is not None and text.strip():
            try:
                result = sentiment_analyzer.analyze(text, lang=item.lang or "es")
                sentiment, sentiment_score = result.label, result.score
            except Exception as exc:  # noqa: BLE001 - sentiment must not break ingest
                log.warning("sentiment analysis failed: %s", exc)

        created = queries.insert_mention(
            session,
            client_id=client_id,
            source=item.source,
            url=item.url,
            keyword_id=keyword.id if keyword else None,
            external_id=item.external_id,
            title=item.title,
            content=item.content,
            author=item.author,
            lang=item.lang,
            published_at=item.published_at,
            reach=item.reach,
            raw=item.raw,
        )
        if created is not None:
            if sentiment is not None:
                created.sentiment = sentiment
                created.sentiment_score = sentiment_score
                session.commit()
            if classifiers:
                _classify_mention(
                    session,
                    mention_id=created.id,
                    text=text,
                    lang=item.lang or "es",
                    classifiers=classifiers,
                )
            inserted += 1
    return inserted


def run_ingest_cycle(
    session: Session,
    *,
    client_id: int,
    keywords: list[Keyword],
    adapters: list[SourceAdapter],
    sentiment_analyzer=None,
    classifiers: Sequence[Classifier] | None = None,
    cycle_started: datetime | None = None,
) -> dict[str, int]:
    """Run every adapter for the client's keywords and persist results.

    Each adapter fetches with its durable ingest watermark (`since`, T2):
    the cursor advances ONLY on a clean pass, so a failing source keeps
    its old watermark and re-covers the missed window next cycle.

    Returns per-adapter inserted counts, e.g. {"google_news": 3, "gdelt": 0}.
    """
    cycle_started = cycle_started or datetime.now(tz=timezone.utc)
    active = [k for k in keywords if k.is_active]
    texts = [k.text for k in active]
    if not texts:
        log.info("client %s: no active keywords, skipping cycle", client_id)
        return {}
    keyword_by_text = {fold_text(k.text): k for k in active}

    stats: dict[str, int] = {}
    for adapter in adapters:
        since = queries.ingest_since(
            session, client_id=client_id, adapter_name=adapter.name
        )
        try:
            items = adapter.fetch(texts, since=since)
        except Exception as exc:  # noqa: BLE001 - one adapter must not kill the cycle
            log.exception("adapter %s failed: %s", adapter.name, exc)
            stats[adapter.name] = 0
            continue
        inserted = persist_raw_mentions(
            session,
            client_id=client_id,
            items=items,
            keyword_by_text=keyword_by_text,
            all_keyword_texts=texts,
            sentiment_analyzer=sentiment_analyzer,
            classifiers=classifiers,
        )
        # Success only: a partial/failed persist must not advance the
        # watermark past items that never landed.
        queries.mark_ingest_success(
            session,
            client_id=client_id,
            adapter_name=adapter.name,
            at=cycle_started,
        )
        stats[adapter.name] = inserted
        log.info(
            "adapter %s: fetched %d items, inserted %d new mentions",
            adapter.name,
            len(items),
            inserted,
        )
    return stats
