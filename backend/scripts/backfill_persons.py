"""One-shot: backfill persons from stored mention enrichments (F3).

Every row with a ``persons`` list inside ``mentions.raw_enrichment`` is a
candidate; the enrichment already did the extraction, this only resolves
identities (app.persons) and writes the links — zero LLM calls, idempotent
(re-running creates no duplicate persons or links).

    PYTHONPATH=backend .venv/bin/python backend/scripts/backfill_persons.py            # dry-run
    PYTHONPATH=backend .venv/bin/python backend/scripts/backfill_persons.py --apply
    PYTHONPATH=backend .venv/bin/python backend/scripts/backfill_persons.py --apply --client-id 3 --limit 500

Dry-run reports candidates and the distinct person names found in the
payloads (an upper bound before dedupe); apply reports per-outcome counts.
"""

import argparse
import logging

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Client, Mention, MentionPerson, Person
from app.persons import persist_persons_from_enrichment

log = logging.getLogger("backfill.persons")


def candidate_rows(
    session, *, client_id: int | None = None, ids: list[int] | None = None
) -> list:
    """(id, raw_enrichment) rows whose payload carries a persons list."""
    stmt = select(Mention.id, Mention.raw_enrichment).order_by(Mention.id)
    if ids is not None:
        stmt = stmt.where(Mention.id.in_(ids))
    if client_id is not None:
        stmt = stmt.where(Mention.client_id == client_id)
    rows = session.execute(stmt).all()
    return [
        (mention_id, payload)
        for mention_id, payload in rows
        if isinstance(payload, dict)
        and isinstance(payload.get("persons"), list)
        and any(
            isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()
            for item in payload["persons"]
        )
    ]


def backfill_persons(
    session, *, client_id: int | None = None, apply: bool = False
) -> dict:
    """Scan candidates; dry-run counts, apply writes links. Counters only."""
    rows = candidate_rows(session, client_id=client_id)
    stats = {
        "candidates": len(rows),
        "distinct_names": len(
            {
                item["name"].strip().lower()
                for _, payload in rows
                for item in payload["persons"]
                if isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip()
            }
        ),
        "links_created": 0,
        "persons_created": 0,
        "errors": 0,
    }
    if not apply:
        return stats

    persons_before = set(
        session.scalars(
            select(Person.id).where(Person.client_id == client_id)
            if client_id is not None
            else select(Person.id)
        )
    )
    for mention_id, _payload in rows:
        try:
            mention = session.get(Mention, mention_id)
            if mention is None:
                continue
            created = persist_persons_from_enrichment(session, mention)
            session.commit()
        except Exception as exc:  # noqa: BLE001 - one row must not stop the scan
            log.warning("backfill failed for mention %s: %s", mention_id, exc)
            session.rollback()
            stats["errors"] += 1
            continue
        stats["links_created"] += created
        if created:
            ids = set(
                session.scalars(
                    select(MentionPerson.person_id).where(
                        MentionPerson.mention_id == mention_id
                    )
                )
            )
            stats["persons_created"] += len(ids - persons_before)
            persons_before |= ids
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write; default is dry-run")
    parser.add_argument("--client-id", type=int, default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    session = SessionLocal()
    try:
        client_ids = (
            [args.client_id] if args.client_id is not None else list(session.scalars(select(Client.id)))
        )
        for client_id in client_ids:
            stats = backfill_persons(session, client_id=client_id, apply=args.apply)
            mode = "apply" if args.apply else "dry-run"
            log.info("client %s backfill (%s): %s", client_id, mode, stats)
    finally:
        session.close()


if __name__ == "__main__":
    main()
