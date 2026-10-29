"""Backfill agenda_items.event_id (mock parity: feed-reactive agenda).

For every agenda item without event, resolves the detonating event by
normalized-title containment — the same criterion the detector now uses at
creation time (app.summaries.agenda_detect._event_link_map). Idempotent:
items with event_id are skipped; --dry-run reports without writing.

Host-runnable against any DATABASE_URL:

    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_agenda_event --dry-run
    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_agenda_event --apply
"""

import argparse
import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AgendaItem, Event
from app.summaries.agenda_detect import _link_event, normalize_title

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill_agenda_event")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write; default dry-run")
    args = parser.parse_args()

    linked = 0
    ambiguous = 0
    with SessionLocal() as session:
        events = session.execute(select(Event.id, Event.client_id, Event.title)).all()
        by_client: dict[int, dict[str, int]] = {}
        for event_id, client_id, title in events:
            key = normalize_title(title or "")
            if key:
                by_client.setdefault(client_id, {})[key] = event_id

        items = session.execute(
            select(AgendaItem).where(AgendaItem.event_id.is_(None))
        ).scalars().all()
        for item in items:
            key = normalize_title(item.title or "")
            if not key:
                continue
            match = _link_event(key, by_client.get(item.client_id, {}))
            if match is None:
                continue
            linked += 1
            if args.apply:
                item.event_id = match
        if args.apply:
            session.commit()
    log.info(
        "%s: %d agendas linked, %d items scanned",
        "APPLIED" if args.apply else "DRY-RUN",
        linked,
        len(items) if items else 0,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
