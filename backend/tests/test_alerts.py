"""Alert engine tests: instant + digest paths, transport, worker wiring.

Every path runs against the shared in-memory SQLite fixture with a fake
transport capturing sends — no SMTP, no network, no model downloads.
"""

import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.alerts import engine
from app.alerts.transport import SmtpTransport
from app.models import (
    AlertDigest,
    AlertSettings,
    Client,
    Mention,
    MentionSource,
    Sentiment,
    make_url_hash,
)
from app.models import queries

NOW = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)


class FakeTransport:
    """Captures every send for assertions."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    def send(self, *, to: str, subject: str, text: str, html: str) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})


@pytest.fixture()
def client(session):
    row = Client(name="acme")
    session.add(row)
    session.commit()
    return row


def make_settings(session, client_id: int, **kwargs) -> AlertSettings:
    settings_row = AlertSettings(
        client_id=client_id,
        digest=kwargs.get("digest", AlertDigest.instant),
        recipient_email=kwargs.get("recipient_email", "ops@acme.com"),
        is_active=kwargs.get("is_active", True),
    )
    session.add(settings_row)
    session.commit()
    return settings_row


def add_mention(session, client_id: int, url: str, **kwargs) -> Mention:
    mention = Mention(
        client_id=client_id,
        source=kwargs.get("source", MentionSource.news_rss),
        url=url,
        url_hash=make_url_hash(url),
        title=kwargs.get("title", "t"),
        content=kwargs.get("content"),
        lang=kwargs.get("lang"),
        sentiment=kwargs.get("sentiment"),
        published_at=kwargs.get("published", NOW),
        ingested_at=kwargs.get("ingested", NOW),
        reach=kwargs.get("reach"),
    )
    session.add(mention)
    session.commit()
    return mention


# ------------------------------------------------------------- instant path


def test_instant_sends_one_batched_email(session, client) -> None:
    make_settings(session, client.id)
    transport = FakeTransport()
    add_mention(
        session,
        client.id,
        "https://a/1",
        title="Uno",
        sentiment=Sentiment.positive,
        ingested=NOW - timedelta(minutes=3),
    )
    add_mention(
        session,
        client.id,
        "https://a/2",
        title="Dos",
        source=MentionSource.x_twitter,
        sentiment=None,
        ingested=NOW - timedelta(minutes=1),
    )

    sent = engine.run_alert_cycle(
        session,
        cycle_started_at=NOW - timedelta(hours=1),
        client_id=client.id,
        transport=transport,
    )

    assert sent == 1
    email = transport.sent[0]
    assert email["to"] == "ops@acme.com"
    assert "2 menciones nuevas" in email["subject"]
    assert "Uno" in email["text"] and "Dos" in email["text"]
    assert "Positiva" in email["text"] and "Sin clasificar" in email["text"]
    assert "[X (Twitter)]" in email["text"]
    assert "<li>" in email["html"] and "Uno" in email["html"]


def test_instant_skips_when_nothing_new(session, client) -> None:
    make_settings(session, client.id)
    add_mention(session, client.id, "https://a/1", ingested=NOW - timedelta(hours=2))
    transport = FakeTransport()

    sent = engine.run_alert_cycle(
        session, cycle_started_at=NOW, client_id=client.id, transport=transport
    )

    assert sent == 0
    assert transport.sent == []


def test_instant_skips_without_active_settings(session, client) -> None:
    transport = FakeTransport()
    add_mention(session, client.id, "https://a/1", ingested=NOW - timedelta(minutes=1))

    # No row at all.
    assert (
        engine.run_alert_cycle(
            session, cycle_started_at=NOW - timedelta(hours=1), client_id=client.id,
            transport=transport,
        )
        == 0
    )

    # Row present but inactive.
    make_settings(session, client.id, is_active=False)
    assert (
        engine.run_alert_cycle(
            session, cycle_started_at=NOW - timedelta(hours=1), client_id=client.id,
            transport=transport,
        )
        == 0
    )
    assert transport.sent == []


def test_instant_caps_body_at_20_mentions(session, client) -> None:
    make_settings(session, client.id)
    for i in range(25):
        add_mention(
            session,
            client.id,
            f"https://a/{i}",
            title=f"M{i}",
            ingested=NOW - timedelta(minutes=30) + timedelta(seconds=i),
        )
    transport = FakeTransport()

    sent = engine.run_alert_cycle(
        session, cycle_started_at=NOW - timedelta(hours=1), client_id=client.id,
        transport=transport,
    )

    assert sent == 1
    text = transport.sent[0]["text"]
    bullets = [line for line in text.splitlines() if line.startswith("- [")]
    assert len(bullets) == 20
    assert "5 más" in text  # overflow pointed to the dashboard


def test_instant_without_smtp_host_logs_instead(session, client, caplog) -> None:
    make_settings(session, client.id)
    add_mention(session, client.id, "https://a/1", ingested=NOW - timedelta(minutes=1))

    with caplog.at_level(logging.INFO, logger="alerts.transport"):
        sent = engine.run_alert_cycle(
            session,
            cycle_started_at=NOW - timedelta(hours=1),
            client_id=client.id,
            transport=None,  # default transport, dev mode (no SMTP_HOST)
        )

    assert sent == 1
    assert any("ops@acme.com" in record.message for record in caplog.records)


# ------------------------------------------------------------- digest path


def test_digest_cycle_only_marks_pending(session, client) -> None:
    cfg = make_settings(session, client.id, digest=AlertDigest.daily)
    add_mention(session, client.id, "https://a/1", ingested=NOW - timedelta(minutes=1))
    transport = FakeTransport()

    sent = engine.run_alert_cycle(
        session, cycle_started_at=NOW - timedelta(hours=1), client_id=client.id,
        transport=transport,
    )

    assert sent == 0
    assert transport.sent == []
    session.expire_all()
    row = queries.get_alert_settings(session, client.id)
    assert row.digest_pending_since is not None
    assert row.last_digest_at is None


def test_daily_digest_sends_counts_and_advances_watermark(session, client) -> None:
    cfg = make_settings(session, client.id, digest=AlertDigest.daily)
    other = Client(name="other")
    session.add(other)
    session.commit()
    add_mention(
        session, client.id, "https://a/1", title="Uno",
        sentiment=Sentiment.positive, ingested=NOW - timedelta(hours=2),
    )
    add_mention(
        session, client.id, "https://a/2", sentiment=None,
        ingested=NOW - timedelta(minutes=30),
    )
    add_mention(
        session, other.id, "https://other/1", title="Otro cliente",
        ingested=NOW - timedelta(minutes=10),
    )
    # Older than the default 1d window: must stay out of the digest.
    add_mention(
        session, client.id, "https://a/3", title="Vieja",
        ingested=NOW - timedelta(days=3),
    )
    transport = FakeTransport()

    sent = engine.run_digest(
        AlertDigest.daily, session=session, client_id=client.id,
        transport=transport, now=NOW,
    )

    assert sent == 1
    email = transport.sent[0]
    assert "Resumen diario" in email["subject"]
    assert "2 menciones nuevas" in email["subject"]
    assert "Positivas: 1" in email["text"]
    assert "Sin clasificar: 1" in email["text"]
    assert "Uno" in email["text"]
    assert "Otro cliente" not in email["text"]  # client-scoped
    assert "Vieja" not in email["text"]  # outside the window

    # Watermark advanced, pending marker cleared, idempotent re-run.
    session.expire_all()
    row = queries.get_alert_settings(session, client.id)
    assert row.last_digest_at is not None
    assert row.digest_pending_since is None
    assert (
        engine.run_digest(
            AlertDigest.daily, session=session, client_id=client.id,
            transport=transport, now=NOW + timedelta(hours=1),
        )
        == 0
    )
    assert len(transport.sent) == 1


def test_digest_window_respects_existing_watermark(session, client) -> None:
    cfg = make_settings(session, client.id, digest=AlertDigest.daily)
    cfg.last_digest_at = NOW - timedelta(minutes=30)
    session.commit()
    add_mention(
        session, client.id, "https://old", title="Pre watermark",
        ingested=NOW - timedelta(hours=1),
    )
    add_mention(
        session, client.id, "https://new", title="Post watermark",
        ingested=NOW - timedelta(minutes=10),
    )
    transport = FakeTransport()

    engine.run_digest(
        AlertDigest.daily, session=session, client_id=client.id,
        transport=transport, now=NOW,
    )

    email = transport.sent[0]
    assert "Post watermark" in email["text"]
    assert "Pre watermark" not in email["text"]


def test_weekly_window_and_kind_mismatch(session, client) -> None:
    make_settings(session, client.id, digest=AlertDigest.weekly)
    add_mention(
        session, client.id, "https/a/old", title="Ocho dias",
        ingested=NOW - timedelta(days=8),
    )
    add_mention(
        session, client.id, "https/a/new", title="Seis dias",
        ingested=NOW - timedelta(days=6),
    )
    transport = FakeTransport()

    # Wrong cadence for this client: nothing sent.
    assert (
        engine.run_digest(
            AlertDigest.daily, session=session, client_id=client.id,
            transport=transport, now=NOW,
        )
        == 0
    )
    # Weekly window covers the 6d-old mention, not the 8d-old one.
    assert (
        engine.run_digest(
            AlertDigest.weekly, session=session, client_id=client.id,
            transport=transport, now=NOW,
        )
        == 1
    )
    text = transport.sent[0]["text"]
    assert "Seis dias" in text and "Ocho dias" not in text


# ------------------------------------------------------------- transport


def test_transport_log_only_without_host(caplog) -> None:
    transport = SmtpTransport(host="", port=587)
    with caplog.at_level(logging.INFO, logger="alerts.transport"):
        transport.send(to="a@b.com", subject="s", text="body", html="<b>body</b>")
    assert any("a@b.com" in record.message for record in caplog.records)


def test_transport_starttls_sends_mime(monkeypatch) -> None:
    import app.alerts.transport as transport_mod

    recorded: dict = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            recorded["connect"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            recorded["starttls"] = True

        def login(self, user, password):
            recorded["login"] = (user, password)

        def send_message(self, message):
            recorded["message"] = message

    monkeypatch.setattr(transport_mod.smtplib, "SMTP", FakeSMTP)
    transport = SmtpTransport(host="smtp.example", port=587, username="u", password="p")

    transport.send(to="dest@acme.com", subject="Asunto", text="hola", html="<b>hola</b>")

    assert recorded["connect"] == ("smtp.example", 587)
    assert recorded["starttls"] is True
    assert recorded["login"] == ("u", "p")
    msg = recorded["message"]
    assert msg["To"] == "dest@acme.com"
    assert msg["Subject"] == "Asunto"
    plain = msg.get_body(preferencelist=("plain",))
    html_part = msg.get_body(preferencelist=("html",))
    assert plain is not None and "hola" in plain.get_content()
    assert html_part is not None and "<b>hola</b>" in html_part.get_content()


def test_transport_ssl_port_465(monkeypatch) -> None:
    import app.alerts.transport as transport_mod

    recorded: dict = {}

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout=None):
            recorded["connect"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_message(self, message):
            recorded["sent"] = True

    monkeypatch.setattr(transport_mod.smtplib, "SMTP_SSL", FakeSMTPSSL)
    transport = SmtpTransport(host="smtp.example", port=465)
    transport.send(to="a@b.com", subject="s", text="t", html="<i>t</i>")

    assert recorded["connect"] == ("smtp.example", 465)
    assert recorded["sent"] is True


# ------------------------------------------------------------- worker wiring


def test_worker_ingest_job_triggers_alerts_best_effort(monkeypatch, session) -> None:
    from app import worker

    calls: list[dict] = []

    def loud_failure(*args, **kwargs):
        calls.append(kwargs)
        raise RuntimeError("smtp down")

    monkeypatch.setattr(worker, "run_alert_cycle", loud_failure)
    monkeypatch.setattr(worker, "run_ingest_cycle", lambda *a, **k: {"google_news": 2})
    monkeypatch.setattr(worker, "build_adapters", lambda: [])
    monkeypatch.setattr(worker, "get_sentiment_analyzer", lambda: None)
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)

    counts = worker.ingest_job()

    assert counts == {"google_news": 2}  # alert failure must not break ingest
    assert len(calls) == 1
    assert "cycle_started_at" in calls[0] and "client_id" in calls[0]


def test_worker_schedules_digest_crons() -> None:
    from zoneinfo import ZoneInfo

    from app import worker

    scheduler = worker.build_scheduler()  # not started
    jobs = {job.id: job for job in scheduler.get_jobs()}
    assert {"ingest_cycle", "alerts_daily", "alerts_weekly"} <= set(jobs)

    now = datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)  # Thursday midday UTC
    daily = jobs["alerts_daily"].trigger.get_next_fire_time(None, now)
    weekly = jobs["alerts_weekly"].trigger.get_next_fire_time(None, now)
    daily_local = daily.astimezone(ZoneInfo("America/Mexico_City"))
    weekly_local = weekly.astimezone(ZoneInfo("America/Mexico_City"))
    assert daily_local.hour == 8
    assert weekly_local.hour == 8 and weekly_local.weekday() == 0


# ------------------------------------------------------------- backfill


class FakeAnalyzer:
    def __init__(self, fail_urls: dict[str, str] | None = None) -> None:
        self.fail_urls = fail_urls or {}
        self.calls: list[tuple[str, str]] = []

    def analyze(self, text: str, lang: str) -> SimpleNamespace:
        self.calls.append((text, lang))
        for url, text_chunk in self.fail_urls.items():
            if text_chunk in text:
                raise RuntimeError("model offline")
        return SimpleNamespace(label=Sentiment.positive, score=0.9)


def test_backfill_fills_missing_and_skips_empty(session, client) -> None:
    from scripts import backfill_sentiment

    m_text = add_mention(
        session, client.id, "https://a/1", title="Hola", content="mundo",
        ingested=NOW,
    )  # sentiment NULL by default
    m_empty = add_mention(
        session, client.id, "https://a/2", title=None, content=None, ingested=NOW
    )
    done = add_mention(session, client.id, "https://a/3", sentiment=Sentiment.negative)
    analyzer = FakeAnalyzer()

    stats = backfill_sentiment.backfill_missing(session, analyzer)

    assert stats == {"backfilled": 1, "skipped_empty": 1, "failed": 0}
    session.expire_all()
    assert m_text.sentiment is Sentiment.positive
    assert m_text.sentiment_score == 0.9
    assert m_empty.sentiment is None  # no text -> nothing to analyze
    assert done.sentiment is Sentiment.negative  # already classified: untouched
    # Spanish default when the row has no language.
    assert analyzer.calls[0][1] == "es"


def test_backfill_analyzer_failure_never_blocks(session, client) -> None:
    from scripts import backfill_sentiment

    add_mention(session, client.id, "https://a/1", title="Hola", content="mundo")
    analyzer = FakeAnalyzer(fail_urls={"https://a/1": "Hola"})

    stats = backfill_sentiment.backfill_missing(session, analyzer)

    assert stats["failed"] == 1
    session.expire_all()
    row = queries.list_mentions(session, client.id)[0]
    assert row.sentiment is None  # stays NULL for a later retry
