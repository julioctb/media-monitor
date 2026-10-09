"""Saved-search spike scans: the persistence side of detect_spike (T2).

`run_spike_scan` is the unit of work behind the worker's `spike_scan_job`:
for every active saved search, bucket the matching mentions hourly over
the trailing window and persist one SpikeEvent per anomalous hour
(idempotent via the (saved_search, window_start) unique key).
"""

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SavedSearch, SpikeEvent, queries
from app.spike.detect import (
    DEFAULT_BASELINE_WINDOW,
    DEFAULT_THRESHOLD,
    detect_spike,
)

log = logging.getLogger("spike.scan")

#: Evaluated bucket: the last COMPLETED hour (partial hours undercount and
#: would mask or fake spikes); the scan runs just after it closes.
SCAN_LAG = timedelta(hours=1)


def _hour_floor(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        # sqlite returns naive datetimes; stored values are UTC by contract.
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.replace(minute=0, second=0, microsecond=0)


def _hourly_buckets(timestamps: list[datetime], first_hour: datetime, hours: int) -> list[tuple]:
    """Zero-filled ascending (hour_start, count) buckets; pure Python so the
    bucketing stays dialect-agnostic (no date_trunc/strftime split)."""
    counts = Counter(_hour_floor(stamp) for stamp in timestamps)
    return [
        (first_hour + timedelta(hours=offset), counts.get(first_hour + timedelta(hours=offset), 0))
        for offset in range(hours)
    ]


def scan_saved_search(
    session: Session,
    saved_search: SavedSearch,
    *,
    now: datetime,
    baseline_window: int = DEFAULT_BASELINE_WINDOW,
    threshold: float = DEFAULT_THRESHOLD,
) -> SpikeEvent | None:
    """Detect and persist at most one new spike for this search, or None."""
    current_hour = _hour_floor(now) - SCAN_LAG
    window_hours = baseline_window + 1
    since = current_hour + timedelta(hours=1) - timedelta(hours=window_hours)
    until = current_hour + timedelta(hours=1)
    timestamps = queries.mention_timestamps(
        session,
        saved_search.client_id,
        since=since,
        until=until,
        **queries.saved_search_filters(saved_search),
    )
    buckets = _hourly_buckets(list(timestamps), since, window_hours)
    event = detect_spike(buckets, baseline_window=baseline_window, threshold=threshold)
    if event is None:
        return None
    duplicate = session.scalar(
        select(SpikeEvent).where(
            SpikeEvent.saved_search_id == saved_search.id,
            SpikeEvent.window_start == event.window_start,
        )
    )
    if duplicate is not None:
        return None
    event.saved_search_id = saved_search.id
    event.client_id = saved_search.client_id
    session.add(event)
    return event


def run_spike_scan(
    session: Session, *, now: datetime | None = None, client_id: int | None = None
) -> list[SpikeEvent]:
    """Scan every active saved search; returns the new events, commit included.

    Per-search failures are logged and skipped so one broken saved search
    cannot stall the sweep.
    """
    moment = now or datetime.now(tz=timezone.utc)
    stmt = select(SavedSearch).where(SavedSearch.is_active.is_(True))
    if client_id is not None:
        stmt = stmt.where(SavedSearch.client_id == client_id)
    events: list[SpikeEvent] = []
    for saved_search in session.scalars(stmt):
        try:
            event = scan_saved_search(session, saved_search, now=moment)
        except Exception:  # noqa: BLE001 - one bad search must not stall the scan
            log.exception("spike scan failed for saved search %s", saved_search.id)
            session.rollback()
            continue
        if event is not None:
            events.append(event)
    if events:
        session.commit()
    return events
