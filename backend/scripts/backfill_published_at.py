"""Backfill published_at for mentions ingested without a date.

Scraper and Google News rows often land with published_at NULL: the
listing page carries no timestamp. Every recency-ordered surface (ask
retrieval, feeds, dedupe windows) ranks NULLs last, so those mentions
effectively vanish. This walks mentions with a fetchable source and a
NULL published_at, re-fetches the article and extracts the date from
meta/JSON-LD/<time>.

Safe to re-run: rows with a date are skipped, failures only log.

Host-runnable against any DATABASE_URL:

    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_published_at --dry-run
    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_published_at --apply --limit 100
"""

import argparse
import logging

from app.db import SessionLocal
from app.ingest.article_fetch import (
    CONTENT_FETCHERS,
    _fetch_page,
    extract_published_at,
)
from app.models import Mention
from sqlalchemy.orm import Session

log = logging.getLogger("backfill.published_at")


def backfill_missing(
    session: Session, *, limit: int | None = None, dry_run: bool = True
) -> dict[str, int]:
    """Fetch a date for every date-less mention with a fetchable source."""
    totals = {"dated": 0, "failed": 0, "skipped_has_date": 0}
    sources = [src for src, fn in CONTENT_FETCHERS.items() if fn is not None]
    query = (
        session.query(Mention)  # type: ignore[attr-defined]
        .filter(Mention.published_at.is_(None), Mention.source.in_(sources))
        .order_by(Mention.id)
    )
    pending = query.all()
    if limit is not None:
        pending = pending[:limit]

    import httpx

    for mention in pending:
        if not mention.url:
            totals["failed"] += 1
            continue
        if dry_run:
            log.info("dry-run: would date mention %s %s", mention.id, mention.url)
            totals["dated"] += 1
            continue
        try:
            with httpx.Client(
                headers={"User-Agent": "media-monitor/0.1 (backfill)"},
                timeout=20,
                follow_redirects=True,
            ) as client:
                html = _fetch_page(mention.url, client)
            published = extract_published_at(html) if html else None
        except Exception as exc:  # noqa: BLE001 - one bad site must not stop the run
            log.warning("fetch failed for mention %s: %s", mention.id, exc)
            published = None
        if published is not None:
            mention.published_at = published
            totals["dated"] += 1
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
            "published_at backfill complete (%s): %s",
            "dry-run" if args.dry_run else "applied",
            totals,
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
