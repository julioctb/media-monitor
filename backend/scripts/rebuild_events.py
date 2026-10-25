"""Rebuild event identity from the mentions source of truth (D3).

The 25/oct coherence pass found mega-events bridged by front-page showcase
posts (one X portada chained presupuesto + pensiones into event 1018, 11
merges deep). Ingest fixes never heal that: events are DERIVED data, so
the honest repair is re-deriving them.

What it does (per client, idempotent by full reset):
1. Clears the arbitration memo (event_merges) — new identity epoch.
2. NULLs every mention.event_id and deletes all events.
3. Re-runs the assigner over ALL mentions chronologically with the current
   rules (D1 aggregate quarantine + D2 media-first canonicals + T1 pools).

Run inside the api container:

    docker cp backend/scripts/rebuild_events.py media-monitor-api-1:/srv/backend/scripts/
    docker exec media-monitor-api-1 python -m scripts.rebuild_events --client-id 1 [--apply]

Afterwards: regen the digests of the affected days and run the healing
sweep (gray band re-judged over the clean identity).
"""

import argparse

from sqlalchemy import delete, select, update

from app.db import SessionLocal
from app.ingest.events import assign_mention_to_event
from app.models import Event, EventMerge, Mention


def _rebuild(session, client_id: int) -> dict[str, int]:
    mentions = list(
        session.scalars(
            select(Mention)
            .where(Mention.client_id == client_id)
            .order_by(Mention.published_at, Mention.ingested_at, Mention.id)
        )
    )
    session.execute(delete(EventMerge).where(EventMerge.client_id == client_id))
    session.execute(
        update(Mention).where(Mention.client_id == client_id).values(event_id=None)
    )
    session.execute(delete(Event).where(Event.client_id == client_id))
    session.flush()

    assigned = 0
    for mention in mentions:
        # Detached event references from the deleted epoch must not leak.
        mention.event = None
        assign_mention_to_event(session, mention)
        if mention.event_id is not None:
            assigned += 1
        # Batched commits keep the transaction bounded on large histories.
        if assigned and assigned % 500 == 0:
            session.commit()
    session.commit()
    events = len(
        session.scalars(
            select(Event.id).where(Event.client_id == client_id)
        ).all()
    )
    return {"mentions": len(mentions), "assigned": assigned, "events": events}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-id", type=int, default=1)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="really rebuild (default: report counts only, no writes)",
    )
    args = parser.parse_args()

    session = SessionLocal()
    try:
        if not args.apply:
            count = len(
                session.scalars(
                    select(Mention.id).where(Mention.client_id == args.client_id)
                ).all()
            )
            print(
                f"dry-run: {count} mentions of client {args.client_id} would be"
                " re-assigned (--apply to rebuild)"
            )
            return 0
        result = _rebuild(session, args.client_id)
        print(f"rebuild: {result}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
