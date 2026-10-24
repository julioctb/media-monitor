"""GET /api/stats/overview: dashboard aggregates."""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter

from app.api.deps import ClientIdDep, SessionDep
from app.api.schemas import (
    ClassifierBreakdown,
    DailyVolume,
    KeywordDayCount,
    StatsDayOut,
    StatsOverview,
    ToneSplit,
)
from app.models import queries
from app.settings_runtime import resolve_effective_settings
from app.summaries.builder import day_window, today_in

router = APIRouter(tags=["stats"])

# ``date`` as a parameter name shadows the datetime type inside the
# signature (same reason schemas.py prebuilds SummaryDate); the optional
# union is built once here instead of inline.
OptionalDay = date | None

VOLUME_DAYS = 30

#: Classifier axes whose rows render on the stats page. Historical values
#: plus the enrichment-persisted ones ('political' now comes from the
#: enrichment pass; 'topic'/'topics' too). Keys of mention_classifications.
CLASSIFIER_NAMES = ("political", "topic", "topics")


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

    def _classification_block() -> list[ClassifierBreakdown]:
        """Per-classifier totals; empty until rows exist."""
        blocks = []
        for name in CLASSIFIER_NAMES:
            breakdown = queries.classification_breakdown(
                session, client_id=client_id, classifier=name
            )
            blocks.append(
                ClassifierBreakdown(
                    classifier=name,
                    total_classified=sum(breakdown.values()),
                    breakdown=breakdown,
                )
            )
        return blocks

    return StatsOverview(
        total=queries.count_mentions(session, client_id),
        by_sentiment=queries.sentiment_breakdown(session, client_id),
        by_source=queries.source_breakdown(session, client_id),
        by_medium=queries.medium_breakdown(session, client_id),
        last_24h=queries.count_mentions(session, client_id, since=now - timedelta(hours=24)),
        last_7d=queries.count_mentions(session, client_id, since=now - timedelta(days=7)),
        daily_volume=daily_volume,
        classifications=_classification_block(),
    )


@router.get("/stats/day", response_model=StatsDayOut)
def stats_day(
    session: SessionDep,
    client_id: ClientIdDep,
    date: OptionalDay = None,
) -> StatsDayOut:
    """Home-page aggregates for one day (home-digest-v2 T2).

    The window is the LOCAL day in the settings timezone — the backend
    mirror of the front's ``zonedDayBounds``; UTC-midnight bounds silently
    push the local evening into the next day. ``date`` defaults to today
    in that timezone. Exposed as a new endpoint so the existing contracts
    (mention page, stored summary, stats overview) stay untouched; the
    tone split and keyword counts are additive reads.
    """
    effective = resolve_effective_settings(session, client_id)
    day = date if date is not None else today_in(effective.timezone)
    start, end = day_window(day, effective.timezone)
    utc_start = start.astimezone(timezone.utc)
    utc_end = end.astimezone(timezone.utc)
    return StatsDayOut(
        date=day,
        timezone=effective.timezone,
        tones=ToneSplit.model_validate(
            queries.tone_split(session, client_id, since=utc_start, until=utc_end)
        ),
        keywords=[
            KeywordDayCount.model_validate(row)
            for row in queries.keyword_day_counts(
                session, client_id, since=utc_start, until=utc_end
            )
        ],
    )
