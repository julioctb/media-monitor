"""Persons API: deduplicated entity list + per-person timeline (F3).

GET /clients/{id}/persons          → ranked list (mentions|recent), `q` filter.
GET /clients/{id}/persons/{pid}    → one person + full mention timeline.

Both tenant-scoped through queries; the timeline is the raw-material feed
for the F4 chat answers (quote + source + url + sentiment + political label).
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Literal

from app.api.deps import SessionDep
from app.api.schemas import PersonDetailOut, PersonOut, PersonTimelineItem
from app.models import Client, queries

router = APIRouter(prefix="/clients/{client_id}/persons", tags=["persons"])


def _client_or_404(session, client_id: int) -> None:
    if session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="client not found")


@router.get("", response_model=list[PersonOut])
def list_persons(
    client_id: int,
    session: SessionDep,
    sort: Literal["mentions", "recent"] = "mentions",
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[PersonOut]:
    """Persons of the client; `mentions` rank (default) or `recent` activity."""
    _client_or_404(session, client_id)
    limit = max(1, min(200, limit))
    rows = queries.list_persons(
        session, client_id, sort=sort, q=q, limit=limit, offset=max(0, offset)
    )
    return [PersonOut.model_validate(row) for row in rows]


@router.get("/{person_id}", response_model=PersonDetailOut)
def person_detail(
    client_id: int,
    person_id: int,
    session: SessionDep,
    limit: int = 100,
) -> PersonDetailOut:
    """One person with the full mention timeline (newest first)."""
    _client_or_404(session, client_id)
    person = queries.get_client_person(session, person_id=person_id, client_id=client_id)
    if person is None:
        raise HTTPException(status_code=404, detail="person not found")
    limit = max(1, min(200, limit))
    timeline = queries.person_timeline(
        session, person_id=person.id, client_id=client_id, limit=limit
    )
    return PersonDetailOut(
        id=person.id,
        name=person.name,
        name_key=person.name_key,
        role=person.role,
        org=person.org,
        aliases=person.aliases or [],
        first_seen_at=person.first_seen_at,
        last_seen_at=person.last_seen_at,
        mention_count=queries.person_mention_count(
            session, person_id=person.id, client_id=client_id
        ),
        timeline=[PersonTimelineItem.model_validate(row) for row in timeline],
    )
