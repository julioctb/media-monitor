"""Sentiment-shift alert rule tests: fires / silent / disabled (T4)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.alerts.engine import SHIFT_WINDOW, check_sentiment_shift
from app.db import get_db
from app.main import create_app
from app.models import (
    AlertSettings,
    Client,
    Mention,
    MentionSource,
    SavedSearch,
    Sentiment,
    queries,
)
from app.models.mention import make_url_hash

NOW = datetime(2026, 10, 11, 12, 0, tzinfo=timezone.utc)


class FakeTransport:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, *, to, subject, text, html) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


@pytest.fixture()
def env(session):
    client = Client(name="acme")
    session.add(client)
    session.commit()
    saved = SavedSearch(client_id=client.id, name="brand", query="brand")
    session.add(saved)
    session.commit()
    cfg = AlertSettings(
        client_id=client.id,
        digest="instant",
        recipient_email="ops@acme.com",
        is_active=True,
    )
    session.add(cfg)
    session.commit()
    return client, saved, cfg


_SEQ = iter(range(100000))


def add_mention(session, client_id, published, sentiment, subject="brand"):
    url = (
        f"https://example.com/{sentiment}/{published.isoformat()}/"
        f"{subject}/{next(_SEQ)}"
    )
    session.add(
        Mention(
            client_id=client_id,
            source=MentionSource.news_rss,
            url=url,
            url_hash=make_url_hash(url),
            title=f"{subject} {sentiment}",
            content=f"{subject} {sentiment} body",
            published_at=published,
            sentiment=sentiment,
        )
    )


def seed_window(session, client_id, start, positive, negative, tag):
    for index in range(positive):
        add_mention(
            session, client_id, start + timedelta(minutes=index), Sentiment.positive, tag
        )
    for index in range(negative):
        add_mention(
            session,
            client_id,
            start + timedelta(minutes=30 + index),
            Sentiment.negative,
            tag,
        )
    session.commit()


def test_shift_fires_and_notifies(session, env):
    client, saved, cfg = env
    # Previous window negative-dominant, current positive-dominant.
    seed_window(session, client.id, NOW - 2 * SHIFT_WINDOW + timedelta(hours=1), 1, 9, "brand")
    seed_window(session, client.id, NOW - SHIFT_WINDOW + timedelta(hours=1), 9, 1, "brand")
    transport = FakeTransport()

    sent = check_sentiment_shift(session, client_id=client.id, now=NOW, transport=transport)
    assert sent == 1
    assert len(transport.sent) == 1
    body = transport.sent[0]["text"]
    assert "brand" in body
    assert cfg.sentiment_shift_last_sent == NOW


def test_no_shift_stays_silent(session, env):
    client, saved, cfg = env
    seed_window(session, client.id, NOW - 2 * SHIFT_WINDOW + timedelta(hours=1), 5, 5, "brand")
    # 9 vs 8: net swing ~5.9 points, below the 10-point default.
    seed_window(session, client.id, NOW - SHIFT_WINDOW + timedelta(hours=1), 9, 8, "brand")
    transport = FakeTransport()

    assert check_sentiment_shift(session, client_id=client.id, now=NOW, transport=transport) == 0
    assert transport.sent == []
    assert cfg.sentiment_shift_last_sent is None


def test_small_shift_below_threshold_silent(session, env):
    client, saved, cfg = env
    # 9 vs 8 classified: ~5.9-point net swing, under the 10 default.
    seed_window(session, client.id, NOW - 2 * SHIFT_WINDOW + timedelta(hours=1), 5, 5, "brand")
    seed_window(session, client.id, NOW - SHIFT_WINDOW + timedelta(hours=1), 9, 8, "brand")
    transport = FakeTransport()
    assert check_sentiment_shift(session, client_id=client.id, now=NOW, transport=transport) == 0

    # Lowering the threshold to 3 makes the same data fire.
    cfg.sentiment_shift_threshold = 3.0
    session.commit()
    transport2 = FakeTransport()
    assert (
        check_sentiment_shift(session, client_id=client.id, now=NOW, transport=transport2) == 1
    )
    assert len(transport2.sent) == 1


def test_disabled_rule_is_silent(session, env):
    client, saved, cfg = env
    cfg.sentiment_shift_enabled = False
    seed_window(session, client.id, NOW - 2 * SHIFT_WINDOW + timedelta(hours=1), 1, 9, "brand")
    seed_window(session, client.id, NOW - SHIFT_WINDOW + timedelta(hours=1), 9, 1, "brand")
    transport = FakeTransport()
    assert check_sentiment_shift(session, client_id=client.id, now=NOW, transport=transport) == 0
    assert transport.sent == []


def test_watermark_prevents_refire_within_window(session, env):
    client, saved, cfg = env
    seed_window(session, client.id, NOW - 2 * SHIFT_WINDOW + timedelta(hours=1), 1, 9, "brand")
    seed_window(session, client.id, NOW - SHIFT_WINDOW + timedelta(hours=1), 9, 1, "brand")
    first = FakeTransport()
    assert check_sentiment_shift(session, client_id=client.id, now=NOW, transport=first) == 1
    # Ten minutes later: same shift, no duplicate email.
    later = FakeTransport()
    assert (
        check_sentiment_shift(
            session, client_id=client.id, now=NOW + timedelta(minutes=10), transport=later
        )
        == 0
    )
    assert later.sent == []
    # After the window elapses it may fire again (fresh windows seeded).
    now2 = NOW + SHIFT_WINDOW
    seed_window(session, client.id, now2 - 2 * SHIFT_WINDOW + timedelta(hours=1), 1, 9, "brand")
    seed_window(session, client.id, now2 - SHIFT_WINDOW + timedelta(hours=1), 9, 1, "brand")
    after = FakeTransport()
    assert (
        check_sentiment_shift(session, client_id=client.id, now=now2, transport=after)
        == 1
    )


def test_unclassified_only_windows_are_skipped(session, env):
    client, saved, cfg = env
    for offset in (1, 25):
        url = f"https://example.com/null/{offset}"
        session.add(
            Mention(
                client_id=client.id,
                source=MentionSource.news_rss,
                url=url,
                url_hash=make_url_hash(url),
                title="brand neutral",
                published_at=NOW - timedelta(hours=offset),
            )
        )
    session.commit()
    transport = FakeTransport()
    assert check_sentiment_shift(session, client_id=client.id, now=NOW, transport=transport) == 0
    assert transport.sent == []  # no ZeroDivision, no email


def test_alert_settings_api_persists_shift_config(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/shift.db")
    from app.models import Base as _Base

    _Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    session.add(Client(name="acme"))
    session.commit()
    app = create_app()

    def override():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override
    with TestClient(app) as api:
        put = api.put(
            "/api/alerts/settings",
            json={
                "digest": "daily",
                "recipient_email": "ops@acme.com",
                "is_active": True,
                "sentiment_shift_enabled": True,
                "sentiment_shift_threshold": 25.0,
            },
        )
        assert put.status_code == 200, put.text
        body = put.json()
        assert body["sentiment_shift_enabled"] is True
        assert body["sentiment_shift_threshold"] == 25.0

        kept = api.put(
            "/api/alerts/settings",
            json={"digest": "daily", "recipient_email": "ops@acme.com", "is_active": True},
        ).json()
        # Absent shift fields keep the stored configuration.
        assert kept["sentiment_shift_threshold"] == 25.0
    session.close()
    engine.dispose()
