"""Spike detection tests: pure math with frozen time + sqlite job run."""

from datetime import datetime, timedelta, timezone

import pytest

from app.models import Client, Mention, MentionSource, SavedSearch
from app.models.mention import make_url_hash
from app.spike import detect_spike
from app.spike.scan import run_spike_scan, scan_saved_search

HOUR = timedelta(hours=1)
T0 = datetime(2026, 9, 1, 6, 0, tzinfo=timezone.utc)


def hourly(counts, start=T0):
    """Buckets ascending, one per hour from `start`."""
    return [(start + index * HOUR, count) for index, count in enumerate(counts)]


def test_spike_fires_on_quiet_baseline():
    baseline = [10, 11, 9, 10, 12, 11, 9, 10] * 4  # 32 noisy buckets, mean 10.25
    buckets = hourly(baseline + [60])
    event = detect_spike(buckets)
    assert event is not None
    assert event.count == 60
    assert event.window_start == T0 + 32 * HOUR
    assert event.window_end == T0 + 33 * HOUR
    assert event.zscore > 2.5
    assert event.baseline_mean == pytest.approx(10.25)


def test_no_spike_when_last_hour_is_normal():
    buckets = hourly([10, 11, 9, 10, 12, 11, 9, 10] * 4 + [10])
    assert detect_spike(buckets) is None


def test_empty_buckets_yield_none():
    assert detect_spike([]) is None


def test_short_history_yields_none():
    # Below MIN_BASELINE_BUCKETS the z-score is noise, not signal.
    buckets = hourly([10, 12, 9, 200])
    assert detect_spike(buckets) is None


def test_threshold_and_baseline_window_are_honored():
    counts = [8, 12] * 15 + [13]  # mean 10, population std 2 over 30 buckets
    buckets = hourly(counts)
    z = (13 - 10) / 2
    assert detect_spike(buckets, threshold=z + 0.1) is None
    event = detect_spike(buckets, threshold=z - 0.1)
    assert event is not None and event.zscore == pytest.approx(z)

    # Trailing-window limit: only the last `baseline_window` buckets count.
    noisy = [100, 4] * 20 + [8, 12] * 15 + [200]
    wide = detect_spike(hourly(noisy), baseline_window=500)
    assert wide is not None
    assert wide.baseline_mean == pytest.approx(34.0)  # full 70-bucket history
    narrow = detect_spike(hourly(noisy), baseline_window=30)
    assert narrow is not None
    assert narrow.baseline_mean == pytest.approx(10.0)  # last 30 only
    assert narrow.zscore > wide.zscore


def test_zero_std_baseline_spikes_only_above_mean():
    event = detect_spike(hourly([7] * 30 + [21]))
    assert event is not None and event.zscore > 2.5
    assert detect_spike(hourly([7] * 30 + [7])) is None


# ------------------------------------------------------------ sqlite job run


def add_mention(session, client_id, published, title="Brand x review", source=None):
    url = f"https://example.com/{source or 'news_rss'}/{published.isoformat()}/{title[:8]}"
    mention = Mention(
        client_id=client_id,
        source=source or MentionSource.news_rss,
        url=url,
        url_hash=make_url_hash(url),
        title=f"{title} {published.isoformat()}",
        published_at=published,
    )
    session.add(mention)
    return mention


@pytest.fixture()
def scenario(session):
    client = Client(name="acme")
    session.add(client)
    session.commit()
    saved = SavedSearch(client_id=client.id, name="brand", query="brand", sources=["news_rss"])
    session.add(saved)
    session.commit()
    return client, saved


def test_scan_persists_spike_once(scenario, session):
    client, saved = scenario
    now = T0.replace(hour=12) + 40 * 24 * HOUR  # far into the timeline
    current_hour = (now - HOUR).replace(minute=0)
    # Quiet baseline: one mention per hour for 3 days.
    for hour_offset in range(24 * 3, 0, -1):
        add_mention(session, client.id, now - hour_offset * HOUR - timedelta(minutes=1))
    # Spike hour: 12 mentions in the last completed hour.
    for index in range(12):
        add_mention(
            session,
            client.id,
            current_hour + timedelta(minutes=index),
            title=f"Brand burst {index}",
        )
    # Off-filter noise: gdelt mentions do not count for this saved search.
    add_mention(session, client.id, current_hour, title="Brand burst x", source=MentionSource.gdelt)
    session.commit()

    events = run_spike_scan(session, now=now)
    assert len(events) == 1
    event = events[0]
    assert event.saved_search_id == saved.id
    assert event.client_id == client.id
    assert event.count == 12  # source filter applied
    assert event.window_start == current_hour

    again = run_spike_scan(session, now=now)
    assert again == []  # dedupe: one event per (search, hour)

    # A later hour with no anomaly adds nothing.
    later = run_spike_scan(session, now=now + 2 * HOUR)
    assert later == []


def test_scan_skips_inactive_and_empty_searches(scenario, session):
    client, saved = scenario
    saved.is_active = False
    session.commit()
    assert run_spike_scan(session, now=T0) == []


def test_scan_saved_search_returns_none_without_history(scenario, session):
    client, saved = scenario
    assert scan_saved_search(session, saved, now=T0) is None
