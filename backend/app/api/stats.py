"""GET /api/stats/overview: dashboard aggregates."""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import DailyVolume, StatsOverview
from app.models import queries

router = APIRouter(tags=["stats"])

VOLUME_DAYS = 30


def _utc_day(value: datetime) -> date:
    """Day bucket of a timestamp; SQLite may hand back naive UTC datetimes."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).date()


@router.get("/stats/overview", response_model=StatsOverview)
def stats_overview(session: SessionDep, client_id: ClientIdDep) -> StatsOverview:
    """Totals, sentiment (incl. NULL bucket) and source breakdowns, recent
    window counts, and per-day volume for the last 30 days (zero-filled)."""
    now = datetime.now(timezone.utc)
    today = now.date()
    start_day = today - timedelta(days=VOLUME_DAYS - 1)
    window_start = datetime.combine(start_day, time.min, tzinfo=timezone.utc)

    day_counts: Counter[date] = Counter(
        _utc_day(published)
        for published in queries.published_dates(session, client_id, since=window_start)
    )
    daily_volume = [
        DailyVolume(
            date=start_day + timedelta(days=offset),
            count=day_counts.get(start_day + timedelta(days=offset), 0),
        )
        for offset in range(VOLUME_DAYS)
    ]

    return StatsOverview(
        total=queries.count_mentions(session, client_id),
        by_sentiment=queries.sentiment_breakdown(session, client_id),
        by_source=queries.source_breakdown(session, client_id),
        last_24h=queries.count_mentions(session, client_id, since=now - timedelta(hours=24)),
        last_7d=queries.count_mentions(session, client_id, since=now - timedelta(days=7)),
        daily_volume=daily_volume,
    )
