"""Person resolution and persistence from stored enrichments (F3).

Persons are NEVER extracted here: the enrichment pass (app.enrich.llm) already
returns ``persons: [{name, role, org, statement, stance}]`` and the full
payload lives on ``mentions.raw_enrichment``. This module only

  1. resolves the entity behind a raw name — ``resolve_person`` dedupes by
     ``fold_text`` name_key plus previously seen aliases, per client;
  2. links the mention to the entity — ``persist_persons_from_enrichment``
     reads the stored JSONB back and writes MentionPerson rows.

Both are idempotent: re-running over the same mention creates no duplicate
persons or links, which is what makes the backfill safe to retry.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.matching import fold_text
from app.models import Mention, MentionPerson, Person

log = logging.getLogger("persons")

#: Hard cap of persons linked per mention (plan F3: hook cap 5).
PERSONS_PER_MENTION = 5


def resolve_person(
    session: Session,
    *,
    client_id: int,
    name: str,
    role: str | None = None,
    org: str | None = None,
    now: datetime | None = None,
) -> Person:
    """Return the client's Person for ``name``, creating it on first sight.

    Matching: exact folded name_key first, then any stored alias key. The
    canonical ``name`` grows to the longest variant seen (better for
    display); ``role``/``org`` are fill-if-empty so the first grounded
    value survives. Every new variant is recorded as an alias.
    """
    cleaned = name.strip()
    key = fold_text(cleaned)
    now = now or datetime.now(tz=timezone.utc)

    person = _match_person(session, client_id=client_id, name=cleaned, key=key)
    if person is None:
        person = Person(
            client_id=client_id,
            name=cleaned,
            name_key=key,
            aliases=[],
            alias_keys="",
            first_seen_at=now,
        )
        session.add(person)
        session.flush()
    else:
        person.last_seen_at = now
        if cleaned != person.name:
            if len(cleaned) > len(person.name):
                # Promote the longer variant to canonical; its key follows and
                # the old canonical degrades to an alias.
                _remember_alias(person, person.name)
                person.name = cleaned
                person.name_key = fold_text(cleaned)
            else:
                _remember_alias(person, cleaned)
    if role and not person.role:
        person.role = role.strip()
    if org and not person.org:
        person.org = org.strip()
    return person


def _token_set(text: str) -> set[str]:
    return frozenset(fold_text(text).split())  # type: ignore[return-value]


def _match_person(
    session: Session, *, client_id: int, name: str, key: str
) -> Person | None:
    """Exact folded name, then a stored alias, then token containment.

    The containment pass is what makes aliases exist at all: news copy refers
    to the same person as "Peña" and later "Peña Nieto"; the first resolve by
    a shorter/longer variant records it as an alias for exact hits afterwards.
    """
    person = session.scalar(
        select(Person).where(Person.client_id == client_id, Person.name_key == key)
    )
    if person is not None:
        return person
    tokens = _token_set(name)
    for candidate in session.scalars(
        select(Person).where(Person.client_id == client_id).order_by(Person.id)
    ):
        if key in _alias_keys_of(candidate):
            return candidate
        seen = _token_set(candidate.name)
        if tokens and (tokens <= seen or seen <= tokens):
            return candidate
    return None


def _alias_keys_of(person: Person) -> list[str]:
    """Stored alias keys, comma-split: keys are folded NAMES, so they
    contain spaces — space-splitting fragmented them and the membership
    guard never hit, duplicating aliases on every enrichment pass."""
    return [key for key in (person.alias_keys or "").split(",") if key]


def _remember_alias(person: Person, variant: str) -> None:
    key = fold_text(variant)
    if key == person.name_key or key in _alias_keys_of(person):
        return
    person.aliases = list(person.aliases) + [variant]
    person.alias_keys = ",".join([*_alias_keys_of(person), key])


def persist_persons_from_enrichment(session: Session, mention: Mention) -> int:
    """Link ``mention`` to the persons named in its stored enrichment.

    Reads ``mentions.raw_enrichment`` (written at ingest/backfill time) —
    no LLM call. Returns the number of NEW links; existing pairs are kept
    as-is, so re-running never duplicates. Rows are only flushed, never
    committed: the caller owns the transaction like the rest of the
    pipeline hooks.
    """
    payload = mention.raw_enrichment
    if not isinstance(payload, dict):
        return 0
    raw_persons = payload.get("persons")
    if not isinstance(raw_persons, list):
        return 0

    # autoflush=False sessions: make prior pending links visible to the
    # dedupe query below (flush only, commit stays with the caller).
    session.flush()
    existing = {
        link.person_id: link
        for link in session.scalars(
            select(MentionPerson).where(MentionPerson.mention_id == mention.id)
        )
    }
    created = 0
    for item in raw_persons[:PERSONS_PER_MENTION]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        role = item.get("role")
        org = item.get("org")
        person = resolve_person(
            session,
            client_id=mention.client_id,
            name=name,
            role=role if isinstance(role, str) else None,
            org=org if isinstance(org, str) else None,
        )
        link = existing.get(person.id)
        if link is None:
            link = MentionPerson(mention_id=mention.id, person_id=person.id)
            session.add(link)
            created += 1
        if isinstance(role, str) and role.strip() and not link.role:
            link.role = role.strip()
        if isinstance(org, str) and org.strip() and not link.org:
            link.org = org.strip()
        context = item.get("statement")
        if isinstance(context, str) and context.strip() and not link.context:
            link.context = context.strip()
    return created
