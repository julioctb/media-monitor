"""Daily summary tests (T11): builder, tz window, LLM gating, API, worker job.

Fully offline: the LLM path is either injected as a callable or faked at
httpx.post; the heuristic path never touches the network.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import create_app
from app.models import (
    Client,
    ClientSettings,
    Keyword,
    MentionSource,
    queries,
)
from app.settings_runtime import EffectiveSettings
from app.summaries import build_daily_summary
from app.summaries.builder import day_window, summary_generator

DAY = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)  # 12:00 in Mexico City

MX_TZ = "America/Mexico_City"


def add_client(session, name="acme") -> Client:
    client = Client(name=name)
    session.add(client)
    session.commit()
    return client


def add_keyword(session, client_id, text, active=True):
    row = Keyword(client_id=client_id, text=text, language="es", is_active=active)
    session.add(row)
    session.commit()
    return row


def add_mention(session, client_id, title, published, *, source=MentionSource.news_rss, keyword_id=None):
    return queries.insert_mention(
        session,
        client_id=client_id,
        source=source,
        url=f"https://example.test/{abs(hash(title))}-{published.timestamp()}",
        title=title,
        keyword_id=keyword_id,
        published_at=published,
    )


# --------------------------------------------------------------------- builder


def test_heuristic_builder_aggregates_sources_keywords_silent(session):
    client = add_client(session)
    buap = add_keyword(session, client.id, "BUAP")
    lilia = add_keyword(session, client.id, "lilia cedillo")
    add_keyword(session, client.id, "sin datos")  # active, no mentions -> silent

    add_mention(session, client.id, "BUAP abre convocatoria", DAY, keyword_id=buap.id)
    add_mention(session, client.id, "Nota general sin keyword", DAY)
    add_mention(
        session,
        client.id,
        "Cedillo encabeza mesa",
        DAY,
        source=MentionSource.x_twitter,
        keyword_id=lilia.id,
    )

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())

    assert row.mode == "heuristic"
    assert row.summary_date == DAY.date()
    content = row.content
    assert content["per_source"]["news_rss"]["count"] == 2
    assert content["per_source"]["x_twitter"]["count"] == 1
    # Newest-first titles, capped at 3.
    assert content["per_source"]["news_rss"]["top_titles"] == [
        "Nota general sin keyword",
        "BUAP abre convocatoria",
    ]
    assert content["per_keyword"]["BUAP"]["count"] == 1
    assert content["per_keyword"]["lilia cedillo"]["top_titles"] == [
        "Cedillo encabeza mesa"
    ]
    assert content["silent_keywords"] == ["sin datos"]
    assert content["totals"] == {
        "mentions": 3,
        "sources": 2,
        "keywords_with_mentions": 2,
        "silent_keywords": 1,
    }
    # Narrative: date, total, dominant source, keyword clauses, silent note.
    assert "9 de octubre de 2026" in row.narrative
    assert "se registraron 3 menciones" in row.narrative
    assert "La fuente dominante fue news_rss" in row.narrative
    assert "Sobre BUAP se registraron 1 mención" in row.narrative
    assert "«BUAP abre convocatoria»" in row.narrative
    assert "Sin menciones: sin datos" in row.narrative
    # Plain text render for RAG: narrative plus every structured section.
    plain = content["plain_text"]
    assert row.narrative in plain
    assert "- news_rss: 2 menciones." in plain
    assert "- BUAP: 1 mención." in plain
    assert "- sin datos: sin menciones." in plain
    # Stored exactly once, readable back through the query helper.
    assert queries.get_daily_summary(session, client.id, DAY.date()).id == row.id


def test_day_window_follows_settings_timezone(session):
    start, end = day_window(DAY.date(), MX_TZ)
    assert start.utcoffset().total_seconds() == -6 * 3600
    assert start.isoformat() == "2026-10-09T00:00:00-06:00"

    client = add_client(session)
    # Oct 9 23:00 CST == Oct 10 05:00Z: inside the MX day, outside UTC's.
    add_mention(
        session,
        client.id,
        "Noche MX",
        datetime(2026, 10, 10, 5, 0, tzinfo=timezone.utc),
    )
    # Oct 9 05:00Z == Oct 8 23:00 CST: the previous MX day.
    add_mention(
        session,
        client.id,
        "Tarde UTC",
        datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc),
    )
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.content["totals"]["mentions"] == 1
    assert row.content["per_source"]["news_rss"]["top_titles"] == ["Noche MX"]
    assert row.content["timezone"] == MX_TZ


def test_llm_mode_with_injected_generator_and_fallback(session):
    client = add_client(session)
    buap = add_keyword(session, client.id, "BUAP")
    add_mention(session, client.id, "BUAP publica", DAY, keyword_id=buap.id)

    captured: dict[str, str] = {}

    def good(prompt: str) -> str:
        captured["prompt"] = prompt
        return "Narrativa generada por el modelo."

    row = build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=good
    )
    assert row.mode == "llm"
    assert row.narrative == "Narrativa generada por el modelo."
    # The prompt carries the verified stats only.
    assert '"per_source"' in captured["prompt"]
    assert "2026-10-09" in captured["prompt"]
    # Structured content is untouched by the narrative rewrite.
    assert row.content["totals"]["mentions"] == 1

    def boom(prompt: str) -> str:
        raise RuntimeError("provider down")

    row = build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=boom
    )
    assert row.mode == "heuristic"
    assert "se registraron 1 mención" in row.narrative


def test_empty_day_stays_heuristic_and_lists_silent(session):
    client = add_client(session)
    add_keyword(session, client.id, "BUAP")

    def unused(prompt: str) -> str:  # pragma: no cover - must not be called
        raise AssertionError("llm must not run for empty days")

    row = build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=unused
    )
    assert row.mode == "heuristic"
    assert "no se registraron menciones" in row.narrative
    assert "Sin cobertura para: BUAP." in row.narrative
    assert row.content["totals"]["mentions"] == 0


def test_summary_generator_gating():
    assert summary_generator(EffectiveSettings(client_id=1)) is None
    assert (
        summary_generator(EffectiveSettings(client_id=1, ai_provider="openai"))
        is None
    )
    callable_gen = summary_generator(
        EffectiveSettings(client_id=1, ai_provider="openai", ai_api_key="sk")
    )
    assert callable(callable_gen)


def test_openai_provider_path_via_fake_http(monkeypatch, session):
    client = add_client(session)
    buap = add_keyword(session, client.id, "BUAP")
    add_mention(session, client.id, "BUAP publica resultados", DAY, keyword_id=buap.id)
    session.add(
        ClientSettings(
            client_id=client.id, ai_provider="openai", ai_api_key="sk-test"
        )
    )
    session.commit()

    calls: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {"message": {"content": " Cierre informativo del modelo. "}}
                ]
            }

    def fake_post(url, **kwargs):
        calls["url"] = url
        calls["json"] = kwargs["json"]
        calls["headers"] = kwargs["headers"]
        return FakeResponse()

    monkeypatch.setattr("app.summaries.builder.httpx.post", fake_post)

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.mode == "llm"
    assert row.narrative == "Cierre informativo del modelo."
    assert calls["url"] == "https://api.openai.com/v1/chat/completions"
    assert calls["headers"]["Authorization"] == "Bearer sk-test"
    body = calls["json"]
    assert body["model"] == "gpt-4o-mini"
    assert body["temperature"] == 0
    assert body["messages"][0]["role"] == "system"
    assert "BUAP" in body["messages"][1]["content"]


def test_upsert_regenerates_same_row(session):
    client = add_client(session)
    buap = add_keyword(session, client.id, "BUAP")
    first = build_daily_summary(session, client_id=client.id, day=DAY.date())
    add_mention(session, client.id, "BUAP amplía", DAY, keyword_id=buap.id)
    second = build_daily_summary(session, client_id=client.id, day=DAY.date())

    assert second.id == first.id
    assert second.content["totals"]["mentions"] == 1
    assert len(queries.list_daily_summaries(session, client.id)) == 1


def test_upsert_noop_keeps_row_stable(session):
    client = add_client(session)
    first = build_daily_summary(session, client_id=client.id, day=DAY.date())
    again = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert again.id == first.id
    assert again.updated_at == first.updated_at


# ------------------------------------------------------------------------- API


@pytest.fixture()
def api(tmp_path):
    """TestClient over a fresh SQLite DB (mirrors test_api.py)."""
    engine = create_engine(f"sqlite:///{tmp_path}/summaries-api.db")
    from app.models import Base

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    client_row = Client(name="acme")
    db.add(client_row)
    db.commit()

    app = create_app()

    def override_db():
        yield db

    from app.api.deps import get_client_id

    def override_client_id():
        return client_row.id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = override_client_id
    with TestClient(app) as test_client:
        yield test_client, db
    db.close()
    engine.dispose()


def test_api_summary_roundtrip(api):
    http, db = api
    client_row = db.query(Client).first()
    client_id = client_row.id

    assert http.get(f"/api/clients/{client_id}/summaries").json() == []
    assert http.get(f"/api/clients/{client_id}/summaries/2026-10-09").json() is None

    buap = add_keyword(db, client_id, "BUAP")
    add_mention(db, client_id, "BUAP publica", DAY, keyword_id=buap.id)

    generated = http.post(
        f"/api/clients/{client_id}/summaries/generate", json={"date": "2026-10-09"}
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["summary_date"] == "2026-10-09"
    assert body["mode"] == "heuristic"
    assert body["content"]["totals"]["mentions"] == 1

    fetched = http.get(f"/api/clients/{client_id}/summaries/2026-10-09").json()
    assert fetched["id"] == body["id"]

    regenerated = http.post(
        f"/api/clients/{client_id}/summaries/generate", json={"date": "2026-10-09"}
    )
    assert regenerated.json()["id"] == body["id"]

    days = http.get(f"/api/clients/{client_id}/summaries").json()
    assert days == [{"summary_date": "2026-10-09", "mode": "heuristic"}]

    # Optional body omitted entirely: defaults to today in the settings tz.
    default_day = http.post(f"/api/clients/{client_id}/summaries/generate")
    assert default_day.status_code == 200
    assert default_day.json()["summary_date"] is not None

    # Empty body object behaves the same.
    empty_body = http.post(
        f"/api/clients/{client_id}/summaries/generate", json={}
    )
    assert empty_body.status_code == 200


def test_api_summary_unknown_client(api):
    http, _db = api
    assert http.get("/api/clients/999/summaries").status_code == 404
    assert (
        http.get("/api/clients/999/summaries/2026-10-09").status_code == 404
    )
    assert (
        http.post("/api/clients/999/summaries/generate", json={}).status_code
        == 404
    )


# ------------------------------------------------------------------ worker job


def test_worker_daily_summary_job(tmp_path, monkeypatch):
    """The job builds today's summary through a real session factory."""
    from app import worker
    from app.summaries import today_in

    engine = create_engine(f"sqlite:///{tmp_path}/worker.db")
    from app.models import Base

    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    session = factory()
    client = Client(name="default")
    session.add(client)
    session.commit()
    client_id = client.id
    session.close()

    monkeypatch.setattr(worker, "SessionLocal", factory)
    monkeypatch.setattr(worker.settings, "default_client_id", client_id)

    assert worker.daily_summary_job() is not None

    check = factory()
    row = queries.get_daily_summary(check, client_id, today_in(MX_TZ))
    check.close()
    assert row is not None
    assert row.mode == "heuristic"
    engine.dispose()


def test_worker_scheduler_has_daily_summary_job(monkeypatch):
    """build_scheduler registers the 21:00 summary cron in the settings tz."""
    from app import worker

    monkeypatch.setattr(worker, "_schedule_timezone", lambda: MX_TZ)
    scheduler = worker.build_scheduler()
    entries = {job.id: job for job in scheduler.get_jobs()}
    job = entries["daily_summary"]
    assert "hour='21'" in str(job.trigger)
    assert "minute='0'" in str(job.trigger)
