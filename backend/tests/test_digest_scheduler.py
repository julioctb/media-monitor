"""Worker multi-cut scheduler: per-hour crons, resync, empty-day skip."""

from datetime import datetime, timedelta, timezone

from app import worker
from app.models import queries


# --- scheduler resync -----------------------------------------------------


class _FakeScheduler:
    """Minimal APScheduler surface used by the resync: jobs by id."""

    def __init__(self, job_ids: list[str]) -> None:
        self._jobs: dict[str, object] = {job_id: object() for job_id in job_ids}
        self.added: list[str] = []
        self.removed: list[str] = []

    def get_jobs(self) -> list:
        return [type("J", (), {"id": job_id})() for job_id in self._jobs]

    def add_job(self, fn, trigger, **kwargs) -> None:
        job_id = kwargs["id"]
        self._jobs[job_id] = fn
        self.added.append(job_id)

    def remove_job(self, job_id: str) -> None:
        del self._jobs[job_id]
        self.removed.append(job_id)


def test_sync_digest_schedule_adds_and_removes(monkeypatch) -> None:
    monkeypatch.setattr(worker, "_digest_hours", lambda: [8, 21])
    monkeypatch.setattr(worker, "_schedule_timezone", lambda: "UTC")
    scheduler = _FakeScheduler(
        [
            "ingest_cycle",
            "alerts_daily",
            f"{worker.DIGEST_JOB_PREFIX}21",
            f"{worker.DIGEST_JOB_PREFIX}9",
        ]
    )

    worker._sync_digest_schedule(scheduler)

    assert scheduler.added == [f"{worker.DIGEST_JOB_PREFIX}8"]
    assert scheduler.removed == [f"{worker.DIGEST_JOB_PREFIX}9"]


def test_sync_digest_schedule_noop_when_aligned(monkeypatch) -> None:
    monkeypatch.setattr(worker, "_digest_hours", lambda: [21])
    monkeypatch.setattr(worker, "_schedule_timezone", lambda: "UTC")
    scheduler = _FakeScheduler(["ingest_cycle", f"{worker.DIGEST_JOB_PREFIX}21"])

    worker._sync_digest_schedule(scheduler)

    assert scheduler.added == []
    assert scheduler.removed == []


def test_build_scheduler_registers_sync_and_cuts(monkeypatch) -> None:
    monkeypatch.setattr(worker, "_schedule_timezone", lambda: "UTC")
    monkeypatch.setattr(worker, "_digest_hours", lambda: [9])
    scheduler = worker.build_scheduler()
    ids = {job.id for job in scheduler.get_jobs()}
    assert f"{worker.DIGEST_JOB_PREFIX}9" in ids
    assert "digest_schedule_sync" in ids
    assert "daily_summary" not in ids  # legacy single job replaced


# --- daily digest skip ----------------------------------------------------


def test_daily_summary_job_skips_empty_day(monkeypatch, session) -> None:
    client = queries.get_or_create_client(session, "default")
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)
    calls: list[tuple] = []

    def fake_builder(session, client_id, day):  # noqa: ANN001
        calls.append((client_id, day))
        return type("R", (), {"id": 1, "mode": "heuristic"})()

    monkeypatch.setattr(worker, "build_daily_summary", fake_builder)
    assert worker.daily_summary_job() is None
    assert calls == []  # no builder call, no row written


def test_daily_summary_job_runs_with_mentions(monkeypatch, session) -> None:
    from app.models import Mention, MentionSource

    client = queries.get_or_create_client(session, "default")
    monkeypatch.setattr(worker, "SessionLocal", lambda: session)
    # A mention inside today's window in the client timezone (UTC storage).
    published = datetime.now(timezone.utc) - timedelta(hours=1)
    session.add(
        Mention(
            client_id=client.id,
            source=MentionSource.news_rss,
            url="https://a/1",
            url_hash="hash-daily-1",
            published_at=published,
        )
    )
    session.commit()
    calls: list[tuple] = []

    def fake_builder(session, client_id, day):  # noqa: ANN001
        calls.append((client_id, day))
        return type("R", (), {"id": 7, "mode": "heuristic"})()

    monkeypatch.setattr(worker, "build_daily_summary", fake_builder)
    assert worker.daily_summary_job() == 7
    assert len(calls) == 1 and calls[0][0] == client.id
