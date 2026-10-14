"""Canonical events API: cluster listing + mention drill-down (Phase 2 T4).

GET /clients/{id}/events        → aggregated events, newest-seen first.
GET /clients/{id}/events/{eid}  → one event + its mentions by reach.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query

from app.api.deps import SessionDep
from app.api.schemas import EventDetailOut, EventMentionOut, EventOut
from app.models import Client, queries

router = APIRouter(prefix="/clients/{client_id}/events", tags=["events"])


def _client_or_404(session, client_id: int) -> None:
    if session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="client not found")


@router.get("", response_model=list[EventOut])
def list_events(
    client_id: int,
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
    since: datetime | None = None,
) -> list[EventOut]:
    """Events of the client, most recently seen first."""
    _client_or_404(session, client_id)
    limit = max(1, min(200, limit))
    rows = queries.list_events(
        session, client_id, limit=limit, offset=max(0, offset), since=since
    )
    return [EventOut.model_validate(row) for row in rows]


@router.get("/{event_id}", response_model=EventDetailOut)
def event_detail(
    client_id: int,
    event_id: int,
    session: SessionDep,
) -> EventDetailOut:
    """One event with its mentions, biggest reach first."""
    _client_or_404(session, client_id)
    event = queries.get_client_event(session, event_id=event_id, client_id=client_id)
    if event is None:
        raise HTTPException(status_code=404, detail="event not found")
    detail = EventDetailOut.model_validate(event)
    detail.mentions = [
        EventMentionOut.model_validate(m)
        for m in queries.event_mentions(session, event.id)
    ]
    return detail
