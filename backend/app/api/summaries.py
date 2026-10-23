"""Daily summary endpoints: /api/clients/{client_id}/summaries (T11).

GET    /summaries          — stored days with their generator mode.
GET    /summaries/{day}    — the row for one day, or null when none stored.
POST   /summaries/generate — build/upsert; body {date?} optional, the
default day is TODAY IN THE SETTINGS TIMEZONE (the client's day, not the
server's), matching the window the nightly worker uses.

Routes carry the client in the path, mirroring saved-searches/spikes.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException

from app.api.deps import SessionDep
from app.api.schemas import (
    DailySummaryOut,
    SummaryDayOut,
    SummaryGenerateRequest,
    SummaryRevisionDayOut,
    SummaryRevisionOut,
    SummaryRevisionRestoreRequest,
)
from app.models import Client, queries
from app.settings_runtime import resolve_effective_settings
from app.summaries import build_daily_summary

router = APIRouter(prefix="/clients/{client_id}", tags=["summaries"])


def _get_client_or_404(session, client_id: int) -> Client:
    client = session.get(Client, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    return client


def _default_day(session, client_id: int) -> date:
    """Today in the client's settings timezone (UTC fallback on bad tz)."""
    effective = resolve_effective_settings(session, client_id)
    try:
        return datetime.now(ZoneInfo(effective.timezone)).date()
    except Exception:  # noqa: BLE001 - mirrors builder._zone's tolerance
        return datetime.now(ZoneInfo("UTC")).date()


@router.get("/summaries", response_model=list[SummaryDayOut])
def list_summary_days(client_id: int, session: SessionDep) -> list[SummaryDayOut]:
    """Stored summary days, newest first (history list)."""
    _get_client_or_404(session, client_id)
    rows = queries.list_daily_summaries(session, client_id)
    return [SummaryDayOut(summary_date=r.summary_date, mode=r.mode) for r in rows]


@router.get("/summary-revisions", response_model=list[SummaryRevisionDayOut])
def list_summary_revision_days(client_id: int, session: SessionDep) -> list[SummaryRevisionDayOut]:
    """Days with stored narrative revisions, newest first."""
    _get_client_or_404(session, client_id)
    return [
        SummaryRevisionDayOut(summary_date=row["summary_date"], count=row["count"], last_at=row["last_at"])
        for row in queries.summary_revision_days(session, client_id)
    ]


@router.get("/summary-revisions/{day}", response_model=list[SummaryRevisionOut])
def list_summary_revisions(day: date, client_id: int, session: SessionDep) -> list[SummaryRevisionOut]:
    """One day's revisions in build order."""
    _get_client_or_404(session, client_id)
    return [
        SummaryRevisionOut.model_validate(row)
        for row in queries.list_summary_revisions(session, client_id, day)
    ]


@router.post("/summary-revisions/restore", response_model=DailySummaryOut)
def restore_summary_revision(
    client_id: int,
    session: SessionDep,
    payload: SummaryRevisionRestoreRequest,
) -> DailySummaryOut:
    """Make revision ``seq`` the live narrative of its day (idempotent)."""
    _get_client_or_404(session, client_id)
    revision = queries.get_summary_revision(session, client_id, payload.day, payload.seq)
    if revision is None:
        raise HTTPException(status_code=404, detail="revision not found")
    row = queries.get_daily_summary(session, client_id, payload.day)
    if row is None:
        raise HTTPException(status_code=404, detail="summary not found")
    row.narrative = revision.narrative
    row.mode = revision.mode
    session.commit()
    session.refresh(row)
    return row


@router.get("/summaries/{day}", response_model=DailySummaryOut | None)
def get_daily_summary(day: date, client_id: int, session: SessionDep):
    """The summary for one day, or null when nothing is stored."""
    _get_client_or_404(session, client_id)
    return queries.get_daily_summary(session, client_id, day)


@router.post("/summaries/generate", response_model=DailySummaryOut)
def generate_daily_summary(
    client_id: int,
    session: SessionDep,
    payload: SummaryGenerateRequest | None = None,
) -> DailySummaryOut:
    """Build (or regenerate) the summary; upsert semantics by contract."""
    _get_client_or_404(session, client_id)
    day = payload.date if payload is not None and payload.date else None
    if day is None:
        day = _default_day(session, client_id)
    return build_daily_summary(session, client_id=client_id, day=day)
