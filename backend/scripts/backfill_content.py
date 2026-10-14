"""Backfill article content for mentions ingested title-only.

Walks every mention whose content is empty and whose source has a
fetcher in app.ingest.article_fetch.CONTENT_FETCHERS, fetches the article
body and stores it. The overflow of the per-cycle ingest cap
(settings.fetch_max_per_cycle, migration 0013) lands here.

Safe to re-run: mentions with content are skipped, fetch failures only
log, and everything commits in one pass at the end.

Host-runnable against any DATABASE_URL:

    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_content --dry-run
    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_content --apply --limit 100
"""

import argparse
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ingest.article_fetch import CONTENT_FETCHERS
from app.models import Mention

log = logging.getLogger("backfill.content")

#: Hard cap per stored body, mirroring the ingest path.
MAX_CONTENT_CHARS = 4000


def backfill_missing(
    session: Session, *, limit: int | None = None, dry_run: bool = True
) -> dict[str, int]:
    """Fetch content for every content-less mention with a fetchable source."""
    totals = {"fetched": 0, "failed": 0, "skipped_has_content": 0}
    query = (
        session.query(Mention)
        .filter(
            Mention.source.in_(  # type: ignore[attr-defined]
                [src for src, fn in CONTENT_FETCHERS.items() if fn is not None]
            )
        )
        .order_by(Mention.id)
    )
    pending = []
    for mention in query.all():
        if mention.content and mention.content.strip():
            totals["skipped_has_content"] += 1
            continue
        pending.append(mention)
    if limit is not None:
        pending = pending[:limit]

    for mention in pending:
        fetcher = CONTENT_FETCHERS.get(mention.source)
        if fetcher is None or not mention.url:
            totals["failed"] += 1
            continue
        if dry_run:
            log.info("dry-run: would fetch mention %s %s", mention.id, mention.url)
            totals["fetched"] += 1
            continue
        try:
            content = fetcher(mention.url)
        except Exception as exc:  # noqa: BLE001 - one bad site must not stop the run
            log.warning("fetch failed for mention %s: %s", mention.id, exc)
            content = None
        if content and content.strip():
            mention.content = content.strip()[:MAX_CONTENT_CHARS]
            totals["fetched"] += 1
        else:
            totals["failed"] += 1

    if not dry_run:
        session.commit()
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="report, do not write")
    mode.add_argument("--apply", action="store_true", help="fetch and store")
    parser.add_argument("--limit", type=int, default=None, help="max mentions this run")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        totals = backfill_missing(session, limit=args.limit, dry_run=args.dry_run)
        log.info(
            "content backfill complete (%s): %s",
            "dry-run" if args.dry_run else "applied",
            totals,
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
