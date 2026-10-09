"""Spike read API: recent spike events for the dashboard (T5)."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas import SpikeOut
from app.models import Client, SavedSearch, SpikeEvent

router = APIRouter(prefix="/clients/{client_id}", tags=["spikes"])


@router.get("/spikes", response_model=list[SpikeOut])
def list_spikes(
    client_id: int,
    session: SessionDep,
    days: int = 30,
    limit: int = 50,
) -> list[SpikeOut]:
    """Most recent spike events across the client's saved searches."""
    if session.get(Client, client_id) is None:
        raise HTTPException(status_code=404, detail="client not found")
    limit = max(1, min(200, limit))
    since = datetime.now(tz=timezone.utc) - timedelta(days=max(1, min(365, days)))
    rows = session.execute(
        select(SpikeEvent, SavedSearch.name)
        .join(SavedSearch, SpikeEvent.saved_search_id == SavedSearch.id)
        .where(SpikeEvent.client_id == client_id, SpikeEvent.window_start >= since)
        .order_by(SpikeEvent.window_start.desc(), SpikeEvent.id.desc())
        .limit(limit)
    )
    return [
        SpikeOut(
            id=event.id,
            saved_search_id=event.saved_search_id,
            saved_search_name=name,
            window_start=event.window_start,
            window_end=event.window_end,
            count=event.count,
            zscore=event.zscore,
            summary=event.summary,
            summary_created_at=event.summary_created_at,
        )
        for event, name in rows.all()
    ]
