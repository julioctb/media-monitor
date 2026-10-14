"""Backfill canonical events for mentions that predate Phase 2.

Walks every mention without event_id that has a title, in publication
order, through the same deterministic assigner the pipeline uses
(app.ingest.events). Safe to re-run: assigned mentions are skipped and
counters derive from the linked rows.

Host-runnable against any DATABASE_URL:

    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_events --dry-run
    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_events --apply
"""

import argparse
import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.ingest.events import assign_mention_to_event
from app.models import Client, Mention

log = logging.getLogger("backfill.events")


def backfill_missing(session: Session, *, dry_run: bool = False) -> dict[str, int]:
    """Assign an event to every event-less mention with a title.

    Per client, mentions ordered by published_at (NULLs last) so pair
    grouping follows chronology, mirroring ingest. dry_run reports the
    would-be counters and the (mention, event-title) pairs without
    writing; the real pass commits once at the end.
    """
    totals = {"assigned": 0, "skipped_no_title": 0, "already_assigned": 0}
    client_ids = list(session.scalars(select(Client.id)))
    pending: list[Mention] = []
    for client_id in client_ids:
        totals["already_assigned"] += int(
            session.scalar(
                select(func.count())
                .select_from(Mention)
                .where(
                    Mention.client_id == client_id,
                    Mention.event_id.is_not(None),
                )
            )
            or 0
        )
        rows = session.scalars(
            select(Mention)
            .where(Mention.client_id == client_id, Mention.event_id.is_(None))
            .order_by(Mention.published_at.asc().nullslast(), Mention.id)
        ).all()
        for mention in rows:
            if not mention.title:
                totals["skipped_no_title"] += 1
                continue
            pending.append(mention)

    for mention in pending:
        if dry_run:
            event = _preview_event(session, mention)
            log.info(
                "dry-run: mention %s (%r) -> %s",
                mention.id,
                mention.title[:80],
                f"event {event.id}" if event else "new event",
            )
            totals["assigned"] += 1
            continue
        assign_mention_to_event(session, mention)
        totals["assigned"] += 1

    if not dry_run:
        session.commit()
    return totals


def _preview_event(session: Session, mention: Mention):
    """The event a dry-run assignment WOULD produce (no writes)."""
    from app.ingest.events import find_or_create_event

    # find_or_create_event flushes a new Event on miss; run it inside a
    # nested transaction that is rolled back right after, keeping the
    # dry-run side-effect free.
    savepoint = session.begin_nested()
    try:
        event = find_or_create_event(
            session,
            client_id=mention.client_id,
            title=mention.title,
            when=mention.published_at or mention.ingested_at,
        )
        session.flush()
    except Exception:
        savepoint.rollback()
        raise
    else:
        event_id = event.id
        savepoint.rollback()
        return session.get(type(event), event_id) if event_id else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="report, do not write")
    mode.add_argument("--apply", action="store_true", help="persist assignments")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        totals = backfill_missing(session, dry_run=args.dry_run)
        log.info("events backfill complete (%s): %s", "dry-run" if args.dry_run else "applied", totals)
    finally:
        session.close()


if __name__ == "__main__":
    main()
