"""Backfill missing sentiment scores through the API analyzer.

Rows with sentiment NULL (analyzer failures never block the insert) are
re-scored in batches. The analyzer is the OpenAI-compatible one, built
from the client's pinned settings; without a configured provider there is
nothing to backfill with. Tests inject a fake analyzer instead.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Client, Mention, queries

log = logging.getLogger("backfill.sentiment")


def _text_of(mention: Mention) -> str:
    parts = [mention.title or "", mention.content or ""]
    return "\n".join(part for part in parts if part)


def backfill_missing(
    session: Session,
    analyzer,
    *,
    batch_size: int = 200,
    limit: int | None = None,
) -> dict[str, int]:
    """Re-score every unclassified mention; returns counters.

    Candidate rows are collected before any write so the offset pagination
    stays stable, then scored and committed in chunks. Analyzer failures
    leave the row NULL for a later retry; text-less rows are skipped.
    """
    totals = {"backfilled": 0, "skipped_empty": 0, "failed": 0}
    client_ids = session.scalars(select(Client.id)).all()
    for client_id in client_ids:
        pending: list[Mention] = []
        offset = 0
        while True:
            batch = queries.list_mentions(
                session, client_id, sentiment_null=True, limit=batch_size, offset=offset
            )
            if not batch:
                break
            pending.extend(batch)
            offset += len(batch)
            if limit is not None and len(pending) >= limit:
                pending = pending[:limit]
                break

        processed = 0
        for mention in pending:
            text = _text_of(mention)
            if not text.strip():
                totals["skipped_empty"] += 1
                continue
            try:
                result = analyzer.analyze(text, lang=mention.lang or "es")
            except Exception as exc:  # noqa: BLE001 - one row must not stop the run
                log.warning(
                    "sentiment backfill failed for mention %s: %s", mention.id, exc
                )
                totals["failed"] += 1
                continue
            mention.sentiment = result.label
            mention.sentiment_score = result.score
            totals["backfilled"] += 1
            processed += 1
            if processed % batch_size == 0:
                session.commit()
        if processed:
            session.commit()
    return totals


def build_analyzer(session):
    """API analyzer from the pinned client settings (the only engine left).

    Returns ``None`` when no OpenAI-compatible provider is configured:
    without it there is nothing to backfill with, by design.
    """
    from app.settings_runtime import resolve_effective_settings

    effective = resolve_effective_settings(session, client_id=1)
    if effective.ai_provider != "openai" or not effective.ai_api_key:
        log.warning("no openai provider configured; sentiment backfill skipped")
        return None
    from app.sentiment.api_analyzer import ApiSentimentAnalyzer

    return ApiSentimentAnalyzer(
        api_key=effective.ai_api_key,
        base_url=effective.ai_base_url,
        model=effective.ai_model,
    )


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        analyzer = build_analyzer(session)
        if analyzer is None:
            return
        stats = backfill_missing(session, analyzer)
        log.info("sentiment backfill complete: %s", stats)
    finally:
        session.close()


if __name__ == "__main__":
    main()
