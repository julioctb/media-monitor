"""Repair duplicated person aliases and rebuild alias_keys.

Historical bug: alias_keys was space-joined but folded names contain
spaces, so the membership guard (`key in alias_keys.split()`) split keys
into single words and never matched — every enrichment pass re-appended
the same alias (Lilia Cedillo had 200+ copies). The fix stores
comma-joined keys; this script dedupes existing alias lists and rebuilds
alias_keys from the surviving variants.

Safe to re-run: idempotent dedupe, reports per-person changes.

    DATABASE_URL=... python -m scripts.repair_person_aliases --dry-run
    DATABASE_URL=... python -m scripts.repair_person_aliases --apply
"""

import argparse
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Person
from app.persons import fold_text

log = logging.getLogger("repair.person_aliases")


def repair_person(person: Person) -> tuple[list[str], list[str]]:
    """Dedupe aliases, rebuild key list. Returns (aliases, alias_keys)."""
    name_key = fold_text(person.name)
    seen: set[str] = {name_key}
    aliases: list[str] = []
    keys: list[str] = []
    for variant in person.aliases or []:
        if not isinstance(variant, str) or not variant.strip():
            continue
        key = fold_text(variant)
        if key in seen:
            continue
        seen.add(key)
        aliases.append(variant.strip())
        keys.append(key)
    return aliases, keys


def repair_all(session: Session, *, dry_run: bool = True) -> dict[str, int]:
    totals = {"persons": 0, "changed": 0, "aliases_removed": 0}
    for person in session.scalars(select(Person)):
        totals["persons"] += 1
        aliases, keys = repair_person(person)
        new_keys = ",".join(keys)
        old_aliases = person.aliases or []
        removed = len(old_aliases) - len(aliases)
        if list(old_aliases) == aliases and (person.alias_keys or "") == new_keys:
            continue
        totals["aliases_removed"] += max(removed, 0)
        totals["changed"] += 1
        if dry_run:
            log.info(
                "dry-run: person %s (%s): %d -> %d aliases",
                person.id,
                person.name,
                len(old_aliases),
                len(aliases),
            )
            continue
        person.aliases = aliases
        person.alias_keys = new_keys
    if not dry_run:
        session.commit()
    return totals


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        totals = repair_all(session, dry_run=args.dry_run)
        log.info(
            "alias repair complete (%s): %s",
            "dry-run" if args.dry_run else "applied",
            totals,
        )
    finally:
        session.close()


if __name__ == "__main__":
    main()
