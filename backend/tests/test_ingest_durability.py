"""Ingest durability tests (T1-T4): cursor, ledger, idempotency, endpoint.

Covers the Phase-1 contract:
- the watermark advances ONLY on a clean adapter pass,
- a failing adapter leaves an error row in the ledger (visible gap),
- re-ingesting the same items is idempotent (url_hash dedupe) and still
  advances the cursor,
- GET /clients/{id}/ingest/runs exposes the ledger.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_client_id
from app.db import get_db
from app.ingest.base import RawMention, SourceAdapter
from app.ingest.pipeline import run_ingest_cycle
from app.main import create_app
from app.models import (
    Base,
    Client,
    IngestCursor,
    IngestRun,
    Keyword,
    Mention,
    MentionSource,
    queries,
)

T1 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def _naive(dt: datetime) -> datetime:
    """SQLite stores TIMESTAMP naive; strip tz for round-trip comparisons."""
    return dt.replace(tzinfo=None)


def _raw(url: str, keyword: str = "BUAP", title: str = "BUAP noticia") -> RawMention:
    return RawMention(
        source=MentionSource.news_rss,
        keyword=keyword,
        url=url,
        title=title,
        published_at=datetime(2026, 10, 12, tzinfo=timezone.utc),
    )


class FakeAdapter(SourceAdapter):
    """Records the `since` it received; optional canned failure."""

    name = "fake"

    def __init__(self, items=None, error: Exception | None = None) -> None:
        self.items = items or []
        self.error = error
        self.seen_since: list[datetime | None] = []

    def fetch(self, keywords, since=None):
        self.seen_since.append(since)
        if self.error is not None:
            raise self.error
        return self.items


@dataclass
class Cycle:
    client: Client
    keywords: list[Keyword]
    adapters: list[SourceAdapter] = field(default_factory=list)


def _cycle(session, name: str = "acme") -> Cycle:
    client = queries.get_or_create_client(session, name)
    kw = Keyword(client_id=client.id, text="BUAP", language="es")
    session.add_all([kw])
    session.commit()
    return Cycle(client=client, keywords=[kw])


def _run(session, cycle: Cycle, started: datetime) -> dict[str, int]:
    return run_ingest_cycle(
        session,
        client_id=cycle.client.id,
        keywords=cycle.keywords,
        adapters=cycle.adapters,
        cycle_started=started,
    )


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/durability.db")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield db
    db.close()
    engine.dispose()


class TestCursorAdvance:
    def test_cursor_advances_on_success_and_since_is_passed(self, session) -> None:
        cycle = _cycle(session)
        adapter = FakeAdapter([_raw("https://example.com/a")])
        cycle.adapters = [adapter]

        stats = _run(session, cycle, started=T1)

        assert stats == {"fake": 1}
        # First run: no watermark yet -> since is None.
        assert adapter.seen_since == [None]
        row = session.query(IngestCursor).one()
        assert row.client_id == cycle.client.id
        assert row.adapter_name == "fake"
        assert row.last_success_at == _naive(T1)

    def test_second_run_fetches_with_overlap_adjusted_since(self, session) -> None:
        cycle = _cycle(session)
        first = FakeAdapter([_raw("https://example.com/a")])
        second = FakeAdapter([_raw("https://example.com/b")])
        cycle.adapters = [first]
        _run(session, cycle, started=T1)
        cycle.adapters = [second]

        _run(session, cycle, started=T1 + timedelta(minutes=30))

        since = second.seen_since[-1]
        assert since is not None
        # watermark (T1) minus default overlap 15 min.
        assert since == _naive(T1 - timedelta(minutes=15))

    def test_cursor_not_advanced_on_adapter_failure(self, session) -> None:
        cycle = _cycle(session)
        ok_run = FakeAdapter([_raw("https://example.com/a")])
        cycle.adapters = [ok_run]
        _run(session, cycle, started=T1)

        broken = FakeAdapter(error=ConnectionError("boom"))
        cycle.adapters = [broken]
        stats = _run(session, cycle, started=T1 + timedelta(minutes=30))

        assert stats == {"fake": 0}
        row = session.query(IngestCursor).one()
        # Still the FIRST success: the failed cycle left no mark.
        assert row.last_success_at == _naive(T1)

    def test_cursor_not_advanced_when_persist_fails(self, session, monkeypatch) -> None:
        cycle = _cycle(session)
        adapter = FakeAdapter([_raw("https://example.com/persist-boom")])
        cycle.adapters = [adapter]

        def boom(*args, **kwargs):
            raise RuntimeError("db write failed")

        monkeypatch.setattr("app.ingest.pipeline.persist_raw_mentions", boom)

        _run(session, cycle, started=T1)

        # persist raised -> ledger error, no cursor row at all.
        assert session.query(IngestCursor).count() == 0
        run_row = session.query(IngestRun).one()
        assert run_row.status == "error"
        assert "db write failed" in run_row.error


class TestLedger:
    def test_error_run_records_exception_and_gap(self, session) -> None:
        cycle = _cycle(session)
        ok_adapter = FakeAdapter()
        ok_adapter.name = "ok_one"
        bad_adapter = FakeAdapter(error=RuntimeError("source down"))
        bad_adapter.name = "bad_one"
        cycle.adapters = [ok_adapter, bad_adapter]

        _run(session, cycle, started=T1)

        rows = {r.adapter_name: r for r in session.query(IngestRun).all()}
        assert rows["ok_one"].status == "ok"
        assert rows["ok_one"].error is None
        assert rows["bad_one"].status == "error"
        assert "source down" in rows["bad_one"].error
        assert rows["bad_one"].inserted == 0
        # Same cycle stamp on both rows: one pass, per-adapter rows.
        assert rows["ok_one"].cycle_started == rows["bad_one"].cycle_started

    def test_every_run_has_duration_and_counts(self, session) -> None:
        cycle = _cycle(session)
        cycle.adapters = [FakeAdapter([_raw("https://example.com/d")])]
        _run(session, cycle, started=T1)

        row = session.query(IngestRun).one()
        assert row.items_seen == 1
        assert row.inserted == 1
        assert row.duration_ms >= 0


class TestIdempotency:
    def test_reingest_same_items_is_idempotent(self, session) -> None:
        cycle = _cycle(session)
        items = [
            _raw("https://example.com/dup", title="BUAP abre inscripciones"),
            _raw("https://example.com/dup2", title="BUAP publica calendario"),
        ]

        first = FakeAdapter(items)
        cycle.adapters = [first]
        stats_one = _run(session, cycle, started=T1)

        # Same items come back on the next cycle (adapter window overlap).
        again = FakeAdapter(items)
        cycle.adapters = [again]
        stats_two = _run(session, cycle, started=T1 + timedelta(minutes=30))

        assert stats_one == {"fake": 2}
        assert stats_two == {"fake": 0}
        assert session.query(Mention).count() == 2
        # ...and the watermark still advanced: the cycle was clean.
        cursor = session.query(IngestCursor).one()
        assert cursor.last_success_at == _naive(T1 + timedelta(minutes=30))
        statuses = [r.status for r in session.query(IngestRun).order_by(IngestRun.id)]
        assert statuses == ["ok", "ok"]


class TestRunsEndpoint:
    @pytest.fixture()
    def api(self, session):
        client_row = queries.get_or_create_client(session, "acme")

        app = create_app()

        def override_db():
            yield session

        def override_client_id():
            return client_row.id

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_client_id] = override_client_id
        with TestClient(app) as test_client:
            yield test_client

    def test_lists_runs_newest_first(self, session, api) -> None:
        cycle = _cycle(session, "acme")
        bad = FakeAdapter(error=RuntimeError("down"))
        bad.name = "bad"
        cycle.adapters = [FakeAdapter([_raw("https://example.com/e")]), bad]
        _run(session, cycle, T1)
        later = FakeAdapter()
        later.name = "bad"
        cycle.adapters = [later]
        _run(session, cycle, T1 + timedelta(hours=1))

        resp = api.get(f"/api/clients/{cycle.client.id}/ingest/runs")

        assert resp.status_code == 200
        rows = resp.json()
        assert rows[0]["cycle_started"] >= rows[-1]["cycle_started"]
        assert len(rows) == 3
        bad_rows = [r for r in rows if r["adapter_name"] == "bad"]
        assert bad_rows[0]["status"] == "ok"  # newest first
        assert bad_rows[-1]["status"] == "error"

    def test_filter_by_adapter_and_status(self, session, api) -> None:
        cycle = _cycle(session, "acme")
        bad = FakeAdapter(error=RuntimeError("down"))
        bad.name = "bad"
        cycle.adapters = [FakeAdapter(), bad]
        _run(session, cycle, T1)

        ok_only = api.get(
            f"/api/clients/{cycle.client.id}/ingest/runs?status=ok"
        ).json()
        assert {r["adapter_name"] for r in ok_only} == {"fake"}
        bad_only = api.get(
            f"/api/clients/{cycle.client.id}/ingest/runs?adapter=bad"
        ).json()
        assert len(bad_only) == 1 and bad_only[0]["status"] == "error"

    def test_unknown_client_404(self, api) -> None:
        assert api.get("/api/clients/9999/ingest/runs").status_code == 404
