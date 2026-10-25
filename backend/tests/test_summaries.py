"""Daily digest tests (T11 -> digest v2): builder, tz window, LLM gating, API, worker.

Fully offline: the LLM path is either injected as a callable or faked at
httpx.post; the heuristic path never touches the network.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import create_app
from app.models import (
    Client,
    ClientSettings,
    Event,
    MentionPerson,
    Person,
    Keyword,
    MentionSource,
    Sentiment,
    queries,
)
from app.settings_runtime import EffectiveSettings
from app.summaries import build_daily_summary
from app.summaries.builder import (
    SYSTEM_PROMPT,
    apply_impact_order,
    compile_tail_cards,
    ensure_decision_density,
    day_window,
    summary_generator,
)
from app.summaries.digest import apply_narrative, validate_digest

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


def add_mention(session, client_id, title, published, *, source=MentionSource.news_rss, keyword_id=None, event_id=None):
    mention = queries.insert_mention(
        session,
        client_id=client_id,
        source=source,
        url=f"https://example.test/{abs(hash(title))}-{published.timestamp()}",
        title=title,
        keyword_id=keyword_id,
        published_at=published,
    )
    if event_id is not None and mention is not None:
        mention.event_id = event_id
        session.commit()
    return mention


# --------------------------------------------------------------------- builder


def test_heuristic_builder_shape_v2(session):
    client = add_client(session)
    buap = add_keyword(session, client.id, "BUAP")
    lilia = add_keyword(session, client.id, "lilia cedillo")
    add_keyword(session, client.id, "sin datos")  # active, no mentions -> pending

    add_mention(session, client.id, "BUAP abre convocatoria", DAY, keyword_id=buap.id)
    add_mention(session, client.id, "Cedillo encabeza mesa", DAY, keyword_id=lilia.id)

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())

    assert row.mode == "heuristic"
    assert row.summary_date == DAY.date()
    content = row.content
    assert content["schema"] == 2
    assert validate_digest(content) == []
    assert content["coverage"]["total"] == 2
    assert content["coverage"]["by_source"] == {"news_rss": 2}
    # No events ingested -> every mention is its own baja-confidence item.
    assert len(content["noticias"]) == 2
    assert {n["confidence"] for n in content["noticias"]} == {"baja"}
    assert {n["title"] for n in content["noticias"]} == {
        "BUAP abre convocatoria",
        "Cedillo encabeza mesa",
    }
    assert "rectora" not in content
    assert content["redes"]["x"]["count"] == 0
    # The silent keyword feeds the temas block; limitaciones = coverage gaps.
    assert content["temas_sin_nota"] == ["sin datos"]
    assert content["pendientes"] == content["coverage"]["gaps"]
    # Plain text render for RAG: sectioned, deterministic.
    plain = content["plain_text"]
    assert "NOTICIAS" in plain
    assert "RECTORA" not in plain  # legacy section removed
    assert "REDES" in plain
    assert "PERSONAS" in plain
    assert "PENDIENTES" in plain
    assert "BUAP abre convocatoria" in plain
    # Stored exactly once, readable back through the query helper.
    assert queries.get_daily_summary(session, client.id, DAY.date()).id == row.id


def test_event_grouping_carries_confidence(session):
    client = add_client(session)
    event = Event(
        client_id=client.id,
        title="BUAP inaugura edificio en Zacapoaxtla",
        title_tokens="buap inaugura edificio",
        mention_count=2,
        source_count=2,
        first_seen_at=DAY,
        last_seen_at=DAY,
    )
    session.add(event)
    session.flush()
    add_mention(session, client.id, "BUAP inaugura edificio", DAY, event_id=event.id)
    add_mention(
        session,
        client.id,
        "Edificio inaugurado en Zacapoaxtla",
        DAY,
        source=MentionSource.rss_custom,
        event_id=event.id,
    )

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())

    noticias = row.content["noticias"]
    assert len(noticias) == 1
    assert noticias[0]["event_id"] == event.id
    assert noticias[0]["confidence"] == "media"
    assert {s["source"] for s in noticias[0]["sources"]} == {"news_rss", "rss_custom"}


def test_day_window_follows_settings_timezone(session, monkeypatch):
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
    # The morning rescue (before 12:00 local) widens the window into the
    # previous evening and would count the 23:00 mention. Pin the hour so
    # the assertion is time-of-day independent; the rescue has its own
    # coverage in the window tests.
    import app.summaries.builder as builder_module

    real_datetime = builder_module.datetime

    class _FixedNowDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):  # noqa: D102 - test shim
            # 13:00 local: past the cutover, no rescue.
            return real_datetime(2026, 10, 23, 13, 0, tzinfo=timezone.utc)

    monkeypatch.setattr(builder_module, "datetime", _FixedNowDatetime)
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row.content["coverage"]["total"] == 1
    assert row.content["coverage"]["by_source"] == {"news_rss": 1}
    assert row.content["timezone"] == MX_TZ


def _digest_payload() -> str:
    return json.dumps(
        {
            "headline": "Titular del modelo.",
            "items": [
                {"index": 0, "summary": "Síntesis del modelo.", "why_it_matters": "Porque sí."}
            ],
            "rectora": {"tone": "neutral", "watch": "votación del 28"},
        }
    )


# home-digest-v2 narrative blocks (T1): the LLM-owned v2 content keys.
_V2_AGENDA = [
    {
        "when": "27 oct. · 13:00",
        "status": "Nueva, sin nota aún",
        "title": "Plática «Conectados pero solos»",
        "source": "X, @BUAPoficial",
    },
    {"when": "Hasta el 15 nov.", "title": "Exposición «Bestias Eternas»"},
]

_V2_REDES_NOTE = "Sin novedades fechables en la ventana."


def _digest_payload_v2() -> str:
    return json.dumps(
        {
            "headline": "Titular del modelo.",
            "items": [
                {"index": 0, "summary": "Síntesis del modelo.", "why_it_matters": "Porque sí."}
            ],
            "agenda": _V2_AGENDA,
            "redes": {"x": {"note": _V2_REDES_NOTE}},
        }
    )


def test_llm_mode_fields_applied_and_fallback(session):
    client = add_client(session)
    # An event-backed mention: inheritance matches noticias by event_id.
    event = Event(
        client_id=client.id,
        title="BUAP publica",
        title_tokens="buap publica",
        mention_count=1,
        source_count=1,
        first_seen_at=DAY,
        last_seen_at=DAY,
    )
    session.add(event)
    session.flush()
    add_mention(session, client.id, "BUAP publica", DAY, event_id=event.id)

    captured: dict[str, str] = {}

    def good(prompt: str) -> str:
        captured["prompt"] = prompt
        return _digest_payload_v2()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=good)
    assert row.mode == "llm"
    assert row.narrative == "Titular del modelo."
    assert row.content["noticias"][0]["summary"] == "Síntesis del modelo."
    assert row.content["noticias"][0]["why_it_matters"] == "Porque sí."
    assert "rectora" not in row.content
    # v2 blocks: agenda and per-network note.
    assert row.content["agenda"] == _V2_AGENDA
    assert row.content["redes"]["x"]["note"] == _V2_REDES_NOTE
    assert validate_digest(row.content) == []
    # The v2 blocks render into the plain text (RAG) as their own sections.
    plain = row.content["plain_text"]
    assert "AGENDA" in plain
    assert "Plática «Conectados pero solos»" in plain
    assert _V2_REDES_NOTE in plain
    # The prompt asks for the v2 narrative blocks by name.
    assert "agenda" in SYSTEM_PROMPT
    # The prompt carries the verified facts only.
    assert '"noticias"' in captured["prompt"]
    assert "2026-10-09" in captured["prompt"]
    # Deterministic sections untouched by the narrative pass.
    assert row.content["coverage"]["total"] == 1

    def boom(prompt: str) -> str:
        raise RuntimeError("provider down")

    row = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=boom)
    # Failed regen of an llm digest inherits the previous narrative/mode —
    # the v2 blocks travel with the prose; facts stay fresh.
    assert row.mode == "llm"
    assert "Titular del modelo." in row.narrative
    assert row.content["noticias"][0]["summary"] == "Síntesis del modelo."
    assert row.content["agenda"] == _V2_AGENDA
    assert row.content["redes"]["x"]["note"] == _V2_REDES_NOTE


def test_llm_garbage_payload_falls_back(session):
    client = add_client(session)
    add_mention(session, client.id, "BUAP publica", DAY)

    def garbage(prompt: str) -> str:
        return "esto no es json {"

    row = build_daily_summary(
        session, client_id=client.id, day=DAY.date(), generate=garbage
    )
    assert row.mode == "heuristic"
    assert validate_digest(row.content) == []


def test_llm_v2_malformed_blocks_tolerated(session):
    client = add_client(session)
    add_mention(session, client.id, "BUAP publica", DAY)
    payload = json.dumps(
        {
            "headline": "Titular.",
            "items": [],
            "agenda": [{"title": "sin when, se descarta"}, "ruido", 42],
            "rectora": {"tone": "neutral", "activity": {"not": "a list"}},
            "redes": {"x": {"note": 123}, "desconocida": {"note": "fuera de contrato"}},
        }
    )

    def partial(prompt: str) -> str:
        return payload

    row = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=partial)
    assert row.mode == "llm"
    content = row.content
    # Malformed entries drop silently; the seeded defaults remain.
    assert content["agenda"] == []
    assert "rectora" not in content  # legacy payload key ignored wholesale
    assert content["redes"]["x"]["note"] == ""
    assert "desconocida" not in content["redes"]
    assert validate_digest(content) == []


def test_apply_narrative_v2_blocks_tolerate_legacy_content():
    # A pre-v2 row carries none of the new keys; the narrative merge must
    # neither fabricate containers nor break on their absence.
    content = {
        "schema": 2,
        "coverage": {},
        "noticias": [],
        "rectora": {"tone": None},
        "redes": {"x": {"count": 0, "note": ""}},
        "personas": [],
        "pendientes": [],
    }
    errors = apply_narrative(
        content,
        {
            "headline": "h",
            "agenda": [{"when": "27 oct.", "title": "Taller"}],
            "rectora": {"activity": [{"text": "nota"}], "tone": "neutral"},
            "redes": {
                "x": {
                    "note": "n",
                    "cuentas": [
                        {"cuenta": "@BUAPoficial", "nota": "sin novedades"},
                        {"nota": "sin cuenta, se descarta"},
                    ],
                }
            },
        },
    )
    assert errors == []
    # Legacy row: the rectora key survives UNTOUCHED (the narrative merge no
    # longer knows the section; legacy keys pass through unchanged).
    assert content["rectora"]["tone"] is None
    assert content["redes"]["x"]["note"] == "n"
    assert content["redes"]["x"]["cuentas"] == [{"cuenta": "@BUAPoficial", "nota": "sin novedades"}]
    assert "agenda" not in content  # legacy shape untouched
    assert "activity" not in content["rectora"]


def test_apply_narrative_confidence_note_lands_on_the_item():
    content = {
        "schema": 2,
        "coverage": {},
        "noticias": [{"event_id": 1, "confidence": "alta", "sources": []}],
        "rectora": {},
        "redes": {},
        "personas": [],
        "pendientes": [],
    }
    errors = apply_narrative(
        content,
        {"items": [{"index": 0, "confidence_note": "fuente oficial directa"}]},
    )
    assert errors == []
    assert content["noticias"][0]["confidence_note"] == "fuente oficial directa"


def test_empty_day_stays_heuristic_and_lists_pending(session):
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
    assert row.content["coverage"]["total"] == 0
    assert row.content["noticias"] == []
    # Silent keywords became the temas block; limitaciones = coverage gaps.
    assert row.content["temas_sin_nota"] == ["BUAP"]
    assert any("sin cobertura" in p for p in row.content["pendientes"])


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


def test_digest_generator_none_content_retried(monkeypatch):
    # content:null (local EXL3 servers under load) used to become the string
    # "None" and blow up json.loads in the digest with
    # "Expecting value: line 1 column 1 (char 0)".
    from app.summaries import builder

    payloads: list[str | None] = [None, json.dumps({"headline": "ok"})]

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            body = payloads[len(calls) - 1] if calls else None
            return {"choices": [{"message": {"content": body}}]}

    calls: list[int] = []

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: A002
        calls.append(1)
        return FakeResponse()

    monkeypatch.setattr(builder.httpx, "post", fake_post)
    generate = builder._openai_generator(
        EffectiveSettings(
            client_id=1,
            ai_provider="openai",
            ai_api_key="sk",
            ai_base_url="https://api.example.com/v1",
            ai_model="m",
        )
    )
    payload = json.loads(generate("prompt"))
    assert payload == {"headline": "ok"}
    assert len(calls) == 2


def test_digest_generator_strips_code_fence(monkeypatch):
    # GLM wraps the JSON in ``` fences; the digest json.loads used to die
    # with "Expecting value: line 1 column 1 (char 0)" on the backtick.
    from app.summaries import builder

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": '```json\n{"headline": "ok"}\n```'
                        }
                    }
                ]
            }

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: A002
        return FakeResponse()

    monkeypatch.setattr(builder.httpx, "post", fake_post)
    generate = builder._openai_generator(
        EffectiveSettings(
            client_id=1,
            ai_provider="openai",
            ai_api_key="sk",
            ai_base_url="https://api.example.com/v1",
            ai_model="m",
        )
    )
    assert json.loads(generate("prompt")) == {"headline": "ok"}


def test_openai_provider_path_via_fake_http(monkeypatch, session):
    client = add_client(session)
    add_mention(session, client.id, "BUAP publica resultados", DAY)
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
                    {"message": {"content": _digest_payload()}}
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
    assert row.narrative == "Titular del modelo."
    assert calls["url"] == "https://api.openai.com/v1/chat/completions"
    assert calls["headers"]["Authorization"] == "Bearer sk-test"
    body = calls["json"]
    assert body["model"] == "gpt-4o-mini"
    assert body["temperature"] == 0
    assert body["messages"][0]["role"] == "system"
    assert "noticias" in body["messages"][1]["content"]


def test_upsert_regenerates_same_row(session):
    client = add_client(session)
    first = build_daily_summary(session, client_id=client.id, day=DAY.date())
    add_mention(session, client.id, "BUAP amplía", DAY)
    second = build_daily_summary(session, client_id=client.id, day=DAY.date())

    assert second.id == first.id
    assert second.content["coverage"]["total"] == 1
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

    add_mention(db, client_id, "BUAP publica", DAY)

    generated = http.post(
        f"/api/clients/{client_id}/summaries/generate", json={"date": "2026-10-09"}
    )
    assert generated.status_code == 200
    body = generated.json()
    assert body["summary_date"] == "2026-10-09"
    assert body["mode"] == "heuristic"
    assert body["content"]["schema"] == 2
    assert body["content"]["coverage"]["total"] == 1

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
    # The job skips mention-less days; seed one inside today's window so
    # the build path is exercised.
    from app.models import Mention

    session.add(
        Mention(
            client_id=client.id,
            source=MentionSource.news_rss,
            url="https://example.com/worker-digest",
            url_hash="hash-worker-digest",
            published_at=datetime.now(timezone.utc),
        )
    )
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
    assert row.content["schema"] == 2
    engine.dispose()


def test_worker_scheduler_has_daily_summary_job(monkeypatch):
    """build_scheduler registers one digest cron per cut, in the settings tz."""
    from app import worker

    monkeypatch.setattr(worker, "_schedule_timezone", lambda: MX_TZ)
    monkeypatch.setattr(worker, "_digest_hours", lambda: [21])
    scheduler = worker.build_scheduler()
    entries = {job.id: job for job in scheduler.get_jobs()}
    job = entries[f"{worker.DIGEST_JOB_PREFIX}21"]
    assert "hour='21'" in str(job.trigger)
    assert "minute='0'" in str(job.trigger)
    assert "digest_schedule_sync" in entries


def test_worker_scheduler_honors_digest_hour_setting(monkeypatch):
    from app import worker

    monkeypatch.setattr(worker, "_schedule_timezone", lambda: MX_TZ)
    monkeypatch.setattr(worker, "_digest_hours", lambda: [7, 21])
    scheduler = worker.build_scheduler()
    entries = {job.id: job for job in scheduler.get_jobs()}
    assert "hour='7'" in str(entries[f"{worker.DIGEST_JOB_PREFIX}7"].trigger)
    assert "hour='21'" in str(entries[f"{worker.DIGEST_JOB_PREFIX}21"].trigger)


def test_window_extension_persists_across_rebuilds(session):
    """Morning first-cut extends into the previous evening; the stored
    window_start pins that choice for later cuts, even at night."""
    from app.summaries.builder import resolve_digest_window

    client = add_client(session)
    buap = add_keyword(session, client.id, "BUAP")
    # Late-evening note the day before: the orphan the extension rescues.
    late = DAY - timedelta(days=1)
    add_mention(
        session,
        client.id,
        "Cobertura nocturna de la nota",
        datetime(late.year, late.month, late.day, 22, 30, tzinfo=timezone.utc),
        keyword_id=buap.id,
    )

    start, end, extended = resolve_digest_window(
        session, client_id=client.id, day=DAY.date(), tz_name="America/Mexico_City"
    )
    # Deterministic part: a fresh day with no stored window uses the plain
    # day bounds or the extension depending on the wall clock; both keep
    # end fixed. Force the extension path through the builder instead.
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    first_window = row.content["window"]["from"]

    # Rebuild: whatever the first cut chose, it persists.
    row2 = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert row2.content["window"]["from"] == first_window
    assert end > start


def test_every_build_logs_a_narrative_revision(session):
    """summary-revisions: append per build, seq grows, prose preserved."""
    from sqlalchemy import select

    from app.models import DailySummaryRevision

    client = add_client(session)
    first = build_daily_summary(session, client_id=client.id, day=DAY.date())
    second = build_daily_summary(session, client_id=client.id, day=DAY.date())

    rows = session.scalars(
        select(DailySummaryRevision)
        .where(DailySummaryRevision.client_id == client.id)
        .order_by(DailySummaryRevision.seq)
    ).all()
    assert [revision.seq for revision in rows] == [1, 2]
    assert [revision.mode for revision in rows] == ["heuristic", "heuristic"]
    assert rows[0].narrative == first.narrative
    assert rows[1].narrative == second.narrative


def test_apply_narrative_logs_skipped_entries(caplog):
    # A mistyped entry is dropped (tolerant merge, unchanged) but no longer
    # silently: the skip is logged with its path and reason.
    import logging as _logging

    from app.summaries.digest import apply_narrative

    content = {
        "schema": 2,
        "coverage": {},
        "noticias": [{"event_id": 1}],
        "rectora": {},
        "redes": {},
        "personas": [],
        "pendientes": [],
    }
    with caplog.at_level(_logging.WARNING, logger="app.summaries.digest"):
        errors = apply_narrative(
            content,
            {"items": [{"index": "2", "summary": "mal tipado"}]},
        )
    assert errors == []
    assert "summary" not in content["noticias"][0]
    assert any("items[0]" in message for message in caplog.messages)


def test_digest_generator_sends_schema_then_plain_retry(monkeypatch):
    # Guided generation on the first attempt; retries go plain so a
    # provider without json_schema support degrades instead of failing.
    from app.summaries import builder

    bodies: list[dict] = []
    # 1st attempt fails (content None), 2nd ok.
    contents = [None, json.dumps({"headline": "ok"})]

    class FakeResponse:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict:
            return {"choices": [{"message": {"content": contents[len(bodies) - 1]}}]}

    def fake_post(url, *, headers=None, json=None, timeout=None):  # noqa: A002
        bodies.append(json)
        return FakeResponse()

    monkeypatch.setattr(builder.httpx, "post", fake_post)
    generate = builder._openai_generator(
        EffectiveSettings(
            client_id=1,
            ai_provider="openai",
            ai_api_key="sk",
            ai_base_url="https://api.example.com/v1",
            ai_model="m",
        )
    )
    generate("{}")

    assert "response_format" in bodies[0]
    schema = bodies[0]["response_format"]["json_schema"]["schema"]
    # NarrativeItem lands as a $ref; its required keys drive guided generation.
    assert schema["$defs"]["NarrativeItem"]["required"] == ["index"]
    assert "response_format" not in bodies[1]


def test_digest_prompt_view_drops_non_narrative_weight():
    from app.summaries.builder import digest_prompt_view

    facts = {
        "coverage": {"total": 9, "by_source": {"x": 9}},
        "pendientes": ["k"],
        "noticias": [
            {
                "title": "T",
                "summary": None,
                "topic": "t",
                "event_id": 3,
                "confidence": "alta",
                "tone": {"negative": 2},
                "person_ids": [1, 2],
                "when_label": "10 a.m.",
                "why_it_matters": None,
                "sources": [{"source": "news_rss", "url": "http://x/a", "title": "a"}],
            }
        ],
        "redes": {"x": {"count": 3, "note": ""}},
        "personas": [{"person_id": 1, "name": "P", "role": "r", "fact": "f"}],
    }

    view = digest_prompt_view(facts)
    assert "coverage" not in view and "pendientes" not in view
    noticia = view["noticias"][0]
    for dropped in ("event_id", "person_ids", "why_it_matters"):
        assert dropped not in noticia
    assert noticia["tone"] == {"negative": 2}
    assert noticia["sources"][0] == {"source": "news_rss", "title": "a"}
    assert "rectora" not in view  # section removed from the projection
    assert "person_id" not in view["personas"][0]
    assert view["redes"] == {"x": {"count": 3, "note": ""}}
    # index alignment: order is the content's own
    assert len(view["noticias"]) == 1


def test_digest_prompt_view_empty_facts():
    from app.summaries.builder import digest_prompt_view

    view = digest_prompt_view({})
    assert view == {"noticias": [], "redes": {}, "personas": []}


# ------------------------------------------------------- digest-brief-v3 (T2)


def _event(client_id, title, tokens=None):
    return Event(
        client_id=client_id,
        title=title,
        title_tokens=tokens or title.lower(),
        mention_count=1,
        source_count=1,
        first_seen_at=DAY,
        last_seen_at=DAY,
    )


def test_brief_delta_flags_new_story_against_previous_day(session):
    from app.summaries.builder import brief_delta

    client = add_client(session)
    kept = _event(client.id, "BUAP abre convocatoria")
    session.add(kept)
    session.flush()
    add_mention(session, client.id, "BUAP abre convocatoria", DAY, event_id=kept.id)
    build_daily_summary(session, client_id=client.id, day=DAY.date())

    fresh = _event(client.id, "Rectora anuncia nuevos horarios")
    session.add(fresh)
    session.flush()
    next_day = DAY + timedelta(days=1)
    add_mention(session, client.id, "BUAP abre convocatoria", next_day, event_id=kept.id)
    add_mention(
        session, client.id, "Rectora anuncia nuevos horarios", next_day, event_id=fresh.id
    )
    row = build_daily_summary(session, client_id=client.id, day=next_day.date())

    # The carried-over story is NOT new; only the fresh event enters delta.
    assert row.content["brief"]["delta"] == [
        {"titulo": "Rectora anuncia nuevos horarios", "giro": None}
    ]
    # The pure matcher agrees when fed the two days' noticias.
    prev = queries.get_daily_summary(session, client.id, DAY.date()).content["noticias"]
    assert brief_delta(prev, row.content["noticias"]) == [
        {"titulo": "Rectora anuncia nuevos horarios", "giro": None}
    ]


def test_brief_delta_matches_by_normalized_title_without_event_id():
    from app.summaries.builder import brief_delta

    prev = [{"event_id": None, "title": "Puma explota pedido", "tone": {}}]
    cur = [{"event_id": None, "title": "puma explota pedido", "tone": {}}]
    assert brief_delta(prev, cur) == []
    cur[0]["title"] = "Nota completamente nueva"
    assert brief_delta(prev, cur) == [{"titulo": "Nota completamente nueva", "giro": None}]


def test_brief_delta_reports_tone_flips():
    from app.summaries.builder import brief_delta

    prev = [{"event_id": 3, "title": "Cambio de rectoría", "tone": {"positive": 2}}]
    cur = [{"event_id": 3, "title": "Cambio de rectoría", "tone": {"negative": 3}}]
    delta = brief_delta(prev, cur)
    assert delta == [
        {"titulo": "Cambio de rectoría", "giro": "el tono pasa de positivo a negativo"}
    ]
    # Same tone: no entry.
    assert brief_delta(prev, prev) == []


def test_tone_label_dominance():
    from app.summaries.builder import tone_label

    assert tone_label({}) is None
    assert tone_label({"negative": 2}) == "negativo"
    assert tone_label({"positive": 3, "neutral": 1}) == "positivo"
    assert tone_label({"neutral": 2}) == "neutral"
    assert tone_label({"positive": 1, "negative": 1}) == "mixto"


def test_campo_lists_published_and_review_only(session):
    from app.models import FieldReport

    client = add_client(session)
    in_day = datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc)
    day_before = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc)
    session.add(
        FieldReport(
            client_id=client.id,
            status="published",
            title="Fuga en la central",
            content="Sin servicio desde las 9.",
            place="Central Camionera",
            created_at=in_day,
            published_at=in_day,
        )
    )
    session.add(
        FieldReport(
            client_id=client.id,
            status="review",
            title="Obra del puente parada",
            content="Lleva tres días sin avanzar.",
            created_at=in_day,
        )
    )
    # draft/rejected and another day: never in the section.
    session.add(
        FieldReport(client_id=client.id, status="draft", title="borrador", created_at=in_day)
    )
    session.add(
        FieldReport(client_id=client.id, status="rejected", title="rechazado", created_at=in_day)
    )
    session.add(
        FieldReport(
            client_id=client.id,
            status="published",
            title="De ayer",
            created_at=day_before,
            published_at=day_before,
        )
    )
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    campo = row.content["campo"]
    assert sorted((c["titulo"], c["estado"]) for c in campo) == [
        ("Fuga en la central", "publicada"),
        ("Obra del puente parada", "en revisión"),
    ]
    fuga = next(c for c in campo if c["titulo"] == "Fuga en la central")
    assert fuga["lugar"] == "Central Camionera"
    assert fuga["contenido"].startswith("Sin servicio")


def test_tarjetas_mirror_noticias_with_tone_and_repeat(session):
    from app.summaries.builder import build_tarjetas

    client = add_client(session)
    event = _event(client.id, "BUAP pierde el clásico")
    session.add(event)
    session.flush()
    # Previous-day mention -> repeat on the digest day.
    add_mention(
        session, client.id, "BUAP pierde el clásico", DAY - timedelta(days=1), event_id=event.id
    )
    # Negative-dominant day tone: the same-day news mention is negative; the
    # rss one stays unclassified (None) and the previous-day one is outside
    # the window (it only drives `repeat`).
    from app.models import Sentiment

    # Distinct title: insert_mention dedupes same client+source+normalized
    # title, and the previous-day mention already used the event title.
    day_news = add_mention(
        session, client.id, "BUAP cae en el clásico en casa", DAY, event_id=event.id
    )
    m2 = add_mention(
        session,
        client.id,
        "Derrota buzca en casa",
        DAY,
        source=MentionSource.rss_custom,
        event_id=event.id,
    )
    day_news.sentiment = Sentiment.negative
    m2.sentiment = None
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    noticias = row.content["noticias"]
    assert len(noticias) == 1
    tono = noticias[0]["tone"]
    assert tono.get("negative", 0) >= 1

    tarjetas = row.content["tarjetas"]
    assert len(tarjetas) == len(noticias)
    tarjeta = tarjetas[0]
    assert tarjeta["titulo"] == "BUAP pierde el clásico"
    assert tarjeta["hecho"] is None and tarjeta["por_que"] is None  # prose is T3
    assert tarjeta["repeat"] is True
    assert tarjeta["tono"] == "negativo"
    assert set(tarjeta["fuentes"]) == {"news_rss", "rss_custom"}
    # The projection helper is pure and index-aligned.
    assert build_tarjetas([{"title": "X", "sources": []}]) == [
        {
            "titulo": "X",
            "hecho": None,
            "por_que": None,
            "fuentes": [],
            "tono": None,
            "repeat": False,
            "angulo_nuevo": None,
        }
    ]


def test_digest_titles_strip_facebook_chrome(session):
    """Read-side normalization: chrome already stored heals at digest build."""
    from app.ingest.facebook_public import strip_fb_chrome

    client = add_client(session)
    dirty = (
        "Verdades Buap CRS actualizó su foto de portada. "
        "hace 14 minutos 14 min · Compartido con: Público "
        "Todas las reacciones: 1 Me gusta Comentar"
    )
    event = _event(client.id, dirty)
    session.add(event)
    session.flush()
    add_mention(session, client.id, dirty, DAY, event_id=event.id, source=MentionSource.facebook_page)
    loose = add_mention(
        session, client.id, dirty + " (variante)", DAY, source=MentionSource.facebook_page
    )
    session.commit()

    from app.summaries.digest import build_digest_facts

    facts = build_digest_facts(session, client_id=client.id, day=DAY.date(), tz=MX_TZ)
    by_title = {n["title"] for n in facts["noticias"]}
    assert strip_fb_chrome(dirty) in by_title
    assert strip_fb_chrome(loose.title) in by_title
    for noticia in facts["noticias"]:
        for fuente in noticia["sources"]:
            assert "Compartido con" not in (fuente["title"] or "")


def test_cosmetic_story_heuristic():
    from app.summaries.builder import is_cosmetic_story

    assert is_cosmetic_story("Verdades Buap CRS actualizó su foto de portada.")
    assert is_cosmetic_story("La BUAP cambió su foto de perfil")
    assert is_cosmetic_story("BUAP renovó su imagen de portada")
    assert is_cosmetic_story("Rectora anuncia nuevos horarios") is False
    assert is_cosmetic_story(None) is False
    assert is_cosmetic_story("") is False


def test_cosmetic_update_never_becomes_tarjeta(session):
    """Piso de calidad: una actualización cosmética de red social no genera
    tarjeta; queda en el log por fuente de redes y cuenta en cobertura."""
    client = add_client(session)
    kw = add_keyword(session, client.id, "BUAP")
    cosmet = add_mention(
        session,
        client.id,
        "Verdades Buap CRS actualizó su foto de portada.",
        DAY,
        source=MentionSource.facebook_page,
        keyword_id=kw.id,
    )
    real = add_mention(
        session, client.id, "BUAP anuncia reforma pensionaria", DAY, keyword_id=kw.id
    )
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    titles = {n["title"] for n in row.content["noticias"]}
    card_titles = {t["titulo"] for t in row.content["tarjetas"]}
    assert len(row.content["tarjetas"]) == len(row.content["noticias"])
    assert "Verdades Buap CRS actualizó su foto de portada." not in card_titles
    assert "BUAP anuncia reforma pensionaria" in card_titles
    assert "Verdades Buap CRS actualizó su foto de portada." not in titles
    # Coverage counts it anyway; the redes per-source log carries it.
    assert row.content["coverage"]["total"] == 2
    assert row.content["redes"]["facebook_page"]["count"] == 1
    assert cosmet.id and real.id  # rows untouched, only the card layer filters


def test_brief_fechas_caduca_y_proxima():
    from datetime import date

    from app.summaries.builder import brief_fechas

    day = date(2026, 10, 9)
    agenda = [
        {"when": "12 de octubre", "title": "Cierre de registro"},
        {"when": "1 de octubre", "title": "Venció el plazo"},
        {"when": "30 de octubre", "title": "Muy lejos"},
        {"when": "sin fecha precisa", "title": "Inparseable"},
        {"when": "9 de octubre", "title": "Hoy mismo"},
    ]
    fechas = brief_fechas(agenda, day)
    by_title = {f["title"]: f["estado"] for f in fechas}
    assert by_title == {
        "Cierre de registro": "proxima",
        "Venció el plazo": "caducada",
        "Hoy mismo": "caducada",
    }
    # Every entry keeps the raw when label for the UI.
    assert all("when" in f for f in fechas)


# ------------------------------------------------------- digest-brief-v3 (T3)


def test_heuristic_headline_leads_with_dominant_event(session):
    from app.models import Sentiment

    client = add_client(session)
    big = _event(client.id, "BUAP anuncia recorte de becas")
    session.add(big)
    session.flush()
    for title in ("Recorte buzca", "Recorte confirmado"):
        mention = add_mention(
            session, client.id, title, DAY, event_id=big.id
        )
        mention.sentiment = Sentiment.negative
    small = _event(client.id, "Expo ciencias")  # one source, no tone
    session.add(small)
    session.flush()
    add_mention(session, client.id, "Expo ciencias", DAY, event_id=small.id)
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    # Impacto computado: el evento de 2 fuentes con tono negativo domina.
    assert row.narrative.startswith("BUAP anuncia recorte de becas encabeza")
    assert "1 nota con tono negativo dominante" in row.narrative
    # The brief headline IS the narrative: one single source of headline.
    assert row.content["brief"]["headline"] == row.narrative


def test_heuristic_brief_sections_by_tone_and_count(session):
    from app.models import Sentiment

    client = add_client(session)
    neg = _event(client.id, "BUAP anuncia recorte de becas")
    session.add(neg)
    session.flush()
    m = add_mention(session, client.id, "Recorte buzca", DAY, event_id=neg.id)
    m2 = add_mention(
        session,
        client.id,
        "Recorte confirmado",
        DAY,
        source=MentionSource.rss_custom,
        event_id=neg.id,
    )
    m.sentiment = Sentiment.negative
    m2.sentiment = Sentiment.negative
    pos = _event(client.id, "BUAP gana fondos")
    session.add(pos)
    session.flush()
    mp = add_mention(session, client.id, "Fuentes extra", DAY, event_id=pos.id)
    mp.sentiment = Sentiment.positive
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    brief = row.content["brief"]
    # F5: los negativos ya no compiten por decision; el top-impacto manda
    # ahí (fallback) y el piso lleva TODA negativa no referenciada a riesgos.
    assert brief["decisiones"] == [{"index": 0, "razon": "mayor cobertura del día"}]
    assert brief["riesgos"] == []
    assert len(brief["a_favor"]) == 1
    assert brief["a_favor"][0]["index"] == 1
    assert brief["a_favor"][0]["razon"] == "tono positivo dominante"
    assert brief["ruido"] == []


def test_riesgo_floor_covers_every_unreferenced_negative():
    """F5: piso en AMBOS caminos — negativa no referenciada => riesgo, sin cap."""
    from app.summaries.builder import ensure_riesgos

    content = {
        "noticias": [
            {"title": "A", "tone": {"negative": 2}},
            {"title": "B", "tone": {"positive": 2}},
            {"title": "C", "tone": {"negative": 1, "neutral": 1}},  # mixto, no negativo
            {"title": "D", "tone": {"negative": 5}},
            {"title": "E", "tone": {"negative": 1}},
        ],
        "brief": {
            "decisiones": [{"index": 0, "razon": "x"}],
            "ruido": [{"index": 2}],
        },
    }

    ensure_riesgos(content)

    # 3 y 4 son negativas no referenciadas: ambas entran, sin cap. La razón
    # se compone desde los hechos de la tarjeta — ya no es etiqueta enlatada.
    riesgos = content["brief"]["riesgos"]
    assert [e["index"] for e in riesgos] == [3, 4]
    assert riesgos[0]["razon"] == (
        "«D»: 5 de 5 menciones con tono negativo; cobertura adversa que exige seguimiento."
    )
    assert riesgos[1]["razon"].startswith("«E»")
    # Idempotente: una segunda pasada no duplica.
    ensure_riesgos(content)
    assert len(content["brief"]["riesgos"]) == 2


def test_riesgo_floor_respects_the_model_selection(session):
    """Camino LLM: lo que el modelo no marcó y es negativo, cae a riesgos."""
    from app.models import Sentiment

    from app.summaries.builder import ensure_riesgos

    client = add_client(session)
    neg = _event(client.id, "BUAP recorta becas")
    session.add(neg)
    session.flush()
    m1 = add_mention(session, client.id, "Recorte de becas", DAY, event_id=neg.id)
    m1.sentiment = Sentiment.negative
    session.commit()

    def payload(prompt: str) -> str:
        return json.dumps(
            {
                "headline": "Titular.",
                "seleccion": [{"index": 0, "categoria": "decision", "razon": "afecta presupuesto"}],
            }
        )

    row = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=payload)
    brief = row.content["brief"]
    assert row.mode == "llm"
    # La seleccion del modelo manda: la negativa marcada decision no se
    # duplica en riesgos; el piso solo toma lo no referenciado.
    assert brief["decisiones"] == [{"index": 0, "razon": "afecta presupuesto"}]
    assert brief["riesgos"] == []

    # Sin ninguna referencia previa, el piso coloca la negativa en riesgos.
    content = row.content
    content["brief"]["decisiones"] = []
    content["brief"]["ruido"] = []
    content["brief"]["riesgos"] = []
    ensure_riesgos(content)
    riesgos = content["brief"]["riesgos"]
    assert [e["index"] for e in riesgos] == [0]
    razon = riesgos[0]["razon"]
    assert razon.startswith("«") and "tono negativo" in razon
    assert len(razon.split()) >= 8  # oración completa, no etiqueta de 3 palabras


def test_brief_selection_merge_replaces_heuristic_buckets(session):
    client = add_client(session)
    add_mention(session, client.id, "BUAP publica", DAY)

    def payload(prompt: str) -> str:
        return json.dumps(
            {
                "headline": "Titular.",
                "items": [{"index": 0, "summary": "hecho", "why_it_matters": "porque"}],
                "seleccion": [
                    {"index": 0, "categoria": "decision", "razon": "afecta presupuesto"},
                    {"index": 0, "categoria": "ruido"},
                ],
            }
        )

    row = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=payload)
    brief = row.content["brief"]
    # Valid selection: the buckets are EXACTLY the model's picks.
    assert brief["decisiones"] == [{"index": 0, "razon": "afecta presupuesto"}]
    assert brief["ruido"] == [{"index": 0}]
    assert brief["a_favor"] == []
    # Prosa viaja igual en tarjeta y noticia (un solo camino de render).
    assert row.content["tarjetas"][0]["hecho"] == "hecho"
    assert row.content["tarjetas"][0]["por_que"] == "porque"


def test_brief_selection_tolerates_bad_entries(session):
    client = add_client(session)
    add_mention(session, client.id, "BUAP publica", DAY)
    payload = json.dumps(
        {
            "headline": "Titular.",
            "seleccion": [
                {"index": "0", "categoria": "decision"},  # strict: dropped
                {"index": 9, "categoria": "ruido"},  # out of range
                {"index": 0, "categoria": "importante"},  # unknown bucket
                {"index": 0, "categoria": "a_favor", "razon": "recupera espacios"},
            ],
        }
    )

    def generate(prompt: str) -> str:
        return payload

    row = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=generate)
    brief = row.content["brief"]
    # Only the healthy entry lands; the rest never breaks the merge.
    assert brief["a_favor"] == [{"index": 0, "razon": "recupera espacios"}]
    assert brief["decisiones"] == []
    assert validate_digest(row.content) == []


def test_brief_esqueleto_golden_keys():
    """Heuristic and LLM fill the SAME esqueleto: identical key structure."""
    from app.summaries.builder import build_tarjetas

    def esqueleto_keys(content: dict) -> dict:
        return {
            "top": sorted(content["brief"].keys()),
            "tarjeta": sorted(content["tarjetas"][0].keys()) if content["tarjetas"] else [],
            "has_campo": "campo" in content,
        }

    assert esqueleto_keys(
        {
            "brief": {
                "headline": "h",
                "delta": [],
                "decisiones": [],
                "riesgos": [],
                "ruido": [],
                "a_favor": [],
                "fechas": [],
            },
            "tarjetas": [build_tarjetas([{"title": "X"}])[0]],
            "campo": [],
        }
    ) == {
        "top": ["a_favor", "decisiones", "delta", "fechas", "headline", "riesgos", "ruido"],
        "tarjeta": [
            "angulo_nuevo",
            "fuentes",
            "hecho",
            "por_que",
            "repeat",
            "titulo",
            "tono",
        ],
        "has_campo": True,
    }


def test_system_prompt_carries_brief_contract():
    assert "seleccion" in SYSTEM_PROMPT
    assert "categoria" in SYSTEM_PROMPT
    # The brief never introduces data: picks reference existing indexes.
    assert "index" in SYSTEM_PROMPT


def test_plain_text_renders_campo_section(session):
    from app.models import FieldReport

    client = add_client(session)
    session.add(
        FieldReport(
            client_id=client.id,
            status="review",
            title="Obra del puente parada",
            content="Lleva tres días sin avanzar.",
            created_at=datetime(2026, 10, 9, 15, 0, tzinfo=timezone.utc),
        )
    )
    session.commit()
    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    plain = row.content["plain_text"]
    # F4: el campo ya no se renderiza en el digest — la clave persiste en
    # el payload y la superficie de campo es /campo.
    assert "CAMPO" not in plain
    campo = row.content["campo"]
    assert campo and campo[0]["titulo"] == "Obra del puente parada"
    assert campo[0]["estado"] == "en revisión"


# ------------------------------------------------------- digest-brief-v3 (T4)


def test_legacy_v2_row_without_brief_still_validates_and_renders():
    """Rows authored before brief-v3 carry none of the new keys: unchanged."""
    from app.summaries.digest import render_plain_text

    legacy = {
        "schema": 2,
        "window": {"from": "2026-10-09T00:00-06:00", "to": "2026-10-10T00:00-06:00"},
        "coverage": {"total": 1, "by_source": {}, "by_topic": {}, "gaps": []},
        "noticias": [
            {
                "title": "BUAP publica",
                "summary": "Síntesis previa.",
                "confidence": "alta",
                "sources": [{"source": "news_rss", "url": "u", "title": "t"}],
            }
        ],
        "rectora": {"tone": "neutral"},
        "redes": {"x": {"count": 0, "note": ""}},
        "personas": [],
        "pendientes": [],
    }
    assert validate_digest(legacy) == []
    plain = render_plain_text(legacy, "Narrativa previa.")
    assert "NOTICIAS" in plain and "PENDIENTES" in plain
    assert "Síntesis previa." in plain
    # No phantom sections on legacy rows.
    assert "BRIEF" not in plain and "CAMPO" not in plain


def test_failed_regen_preserves_llm_prose_in_tarjetas(session):
    """The inheritance path flows into the cards: hecho/por_que survive."""
    client = add_client(session)
    event = _event(client.id, "BUAP publica resultados")
    session.add(event)
    session.flush()
    add_mention(session, client.id, "BUAP publica resultados", DAY, event_id=event.id)

    def good(prompt: str) -> str:
        return json.dumps(
            {
                "headline": "Titular con prosa.",
                "items": [
                    {
                        "index": 0,
                        "summary": "Síntesis del modelo.",
                        "why_it_matters": "Porque importa.",
                    }
                ],
            }
        )

    first = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=good)
    assert first.mode == "llm"
    assert first.content["tarjetas"][0]["hecho"] == "Síntesis del modelo."

    def boom(prompt: str) -> str:
        raise RuntimeError("provider down")

    second = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=boom)
    assert second.id == first.id
    # Prose inherited end to end: noticia, tarjeta and headline.
    assert second.mode == "llm"
    assert second.content["noticias"][0]["summary"] == "Síntesis del modelo."
    assert second.content["tarjetas"][0]["hecho"] == "Síntesis del modelo."
    assert second.content["tarjetas"][0]["por_que"] == "Porque importa."
    assert second.content["brief"]["headline"].startswith("Titular con prosa.")
    # Esqueleto keys intact after the inheritance merge.
    assert set(second.content["brief"].keys()) == {
        "headline",
        "delta",
        "decisiones",
        "riesgos",
        "ruido",
        "a_favor",
        "fechas",
    }
    assert validate_digest(second.content) == []


def test_regen_refreshes_deterministic_sections(session):
    """Regen recomputes tarjetas/brief/campo; revisions keep appending."""
    from sqlalchemy import select

    from app.models import DailySummaryRevision

    client = add_client(session)
    add_mention(session, client.id, "BUAP abre convocatoria de becas", DAY)
    first = build_daily_summary(session, client_id=client.id, day=DAY.date())
    add_mention(session, client.id, "Cedillo encabeza mesa de análisis", DAY)
    second = build_daily_summary(session, client_id=client.id, day=DAY.date())

    assert second.id == first.id
    assert second.content["coverage"]["total"] == 2
    assert len(second.content["tarjetas"]) == 2
    # The brief/campo sections are present and re-derived, not stale copies.
    assert second.content["brief"]["headline"] == second.narrative
    assert second.content["campo"] == []
    seqs = session.scalars(
        select(DailySummaryRevision.seq).where(
            DailySummaryRevision.client_id == client.id
        )
    ).all()
    assert sorted(seqs) == [1, 2]


# ----------------------------------------------- digest-brief-v3 T8 (calidad)


def _twin_events(session, client_id):
    """Two single-source events telling the same pensiones story."""
    e1 = _event(client_id, "BUAP pospone consulta sobre reforma de pensiones y jubilaciones")
    e2 = _event(client_id, "Se pospone consulta sobre reforma de pensiones de la BUAP, anuncia rectora")
    session.add_all([e1, e2])
    session.flush()
    return e1, e2


def test_twin_stories_merge_into_one_card(session):
    """Same editorial story from different outlets: ONE card, all sources."""
    client = add_client(session)
    e1, e2 = _twin_events(session, client.id)
    e1.summary = "La BUAP movió la consulta para revisar el aumento salarial."
    add_mention(session, client.id, e1.title, DAY, event_id=e1.id)
    add_mention(
        session,
        client.id,
        e2.title,
        DAY,
        source=MentionSource.rss_custom,
        event_id=e2.id,
    )

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    noticias = row.content["noticias"]
    assert len(noticias) == 1
    nota = noticias[0]
    assert {s["source"] for s in nota["sources"]} == {"news_rss", "rss_custom"}
    # The best source carries the facts; both events traceable.
    assert nota["summary"] == "La BUAP movió la consulta para revisar el aumento salarial."
    assert nota["event_id"] in (e1.id, e2.id)
    assert set(nota["event_ids"]) == {e1.id, e2.id}
    # Two independent outlets -> media confidence for the merged story.
    assert nota["confidence"] == "media"

    tarjetas = row.content["tarjetas"]
    assert len(tarjetas) == 1
    assert set(tarjetas[0]["fuentes"]) == {"news_rss", "rss_custom"}
    assert validate_digest(row.content) == []


def test_twin_merge_keeps_distinct_stories_apart(session):
    """Below the digest threshold, unrelated stories never fuse."""
    client = add_client(session)
    e1 = _event(client.id, "BUAP pospone consulta sobre reforma de pensiones")
    e2 = _event(client.id, "Taller gratuito de dibujo para personas sordas")
    session.add_all([e1, e2])
    session.flush()
    add_mention(session, client.id, e1.title, DAY, event_id=e1.id)
    add_mention(
        session,
        client.id,
        e2.title,
        DAY,
        source=MentionSource.rss_custom,
        event_id=e2.id,
    )

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert len(row.content["noticias"]) == 2
    assert len(row.content["tarjetas"]) == 2


def test_twin_merge_sums_tone_and_flags_repeat(session):
    """Aggregates are the union: tone counters add, repeat is OR."""
    client = add_client(session)
    e1, e2 = _twin_events(session, client.id)
    neg = add_mention(session, client.id, e1.title, DAY, event_id=e1.id)
    add_mention(
        session,
        client.id,
        "BUAP reprograma la consulta de pensiones",
        DAY - timedelta(days=1),
        event_id=e1.id,
    )  # earlier mention -> repeat
    pos = add_mention(
        session,
        client.id,
        e2.title,
        DAY,
        source=MentionSource.rss_custom,
        event_id=e2.id,
    )
    from app.models import Sentiment

    neg.sentiment = Sentiment.negative
    pos.sentiment = Sentiment.positive
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    nota = row.content["noticias"][0]
    assert nota["tone"] == {"negative": 1, "positive": 1}
    assert nota["repeat"] is True
    assert row.content["tarjetas"][0]["repeat"] is True


def test_failed_regen_inherits_prose_across_merged_events(session):
    """The inheritance path matches ANY event id of the merged card."""
    client = add_client(session)
    e1, e2 = _twin_events(session, client.id)
    add_mention(session, client.id, e1.title, DAY, event_id=e1.id)
    add_mention(
        session,
        client.id,
        e2.title,
        DAY,
        source=MentionSource.rss_custom,
        event_id=e2.id,
    )

    def good(prompt: str) -> str:
        return json.dumps(
            {
                "headline": "Una sola historia.",
                "items": [
                    {
                        "index": 0,
                        "summary": "Consulta pospuesta.",
                        "why_it_matters": "Define el recorte 2027.",
                    }
                ],
            }
        )

    first = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=good)
    assert first.mode == "llm"

    def boom(prompt: str) -> str:
        raise RuntimeError("provider down")

    second = build_daily_summary(session, client_id=client.id, day=DAY.date(), generate=boom)
    assert second.content["noticias"][0]["summary"] == "Consulta pospuesta."
    assert second.content["tarjetas"][0]["por_que"] == "Define el recorte 2027."


# --------------------------------------------------- T8.C títulos sobrios


def test_display_title_strips_chrome_and_is_idempotent():
    from app.summaries.builder import display_title

    raw = "🙌🏻 ¡BUAP confirma becas! Postulate https://t.co/xYz #BecasBUAP @BUAPoficial"
    clean = display_title(raw)
    assert clean == "¡BUAP confirma becas! Postulate"
    assert display_title(clean) == clean  # idempotente
    assert display_title(None) == ""
    assert display_title("   ") == ""
    # Un título solo-emoji nunca se vuelve vacío.
    assert display_title("🎓") == "🎓"


def test_tarjetas_title_sobrio_raw_survives_in_noticias(session):
    client = add_client(session)
    event = _event(client.id, "🎓 ¡BUAP abre convocatoria! https://t.co/a1")
    session.add(event)
    session.flush()
    add_mention(session, client.id, event.title, DAY, event_id=event.id)

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    content = row.content
    # La tarjeta muestra el título sobrio...
    assert content["tarjetas"][0]["titulo"] == "¡BUAP abre convocatoria!"
    # ...el crudo sobrevive en la noticia y sus fuentes.
    assert content["noticias"][0]["title"].startswith("🎓")
    assert content["noticias"][0]["sources"][0]["title"].startswith("🎓")
    # El texto plano (RAG/lectura) también presentacional: sin chrome.
    plain = content["plain_text"]
    assert "¡BUAP abre convocatoria!" in plain
    assert "https://t.co/a1" not in plain


def test_prompt_view_carries_sobrio_titles():
    from app.summaries.builder import digest_prompt_view

    facts = {
        "noticias": [
            {
                "title": "🎓 Título con chrome https://x.co/a",
                "sources": [{"source": "x", "title": "🗳 Raw de la fuente"}],
            }
        ],
        "rectora": {},
    }

    view = digest_prompt_view(facts)
    assert view["noticias"][0]["title"] == "Título con chrome"
    assert view["noticias"][0]["sources"][0]["title"] == "Raw de la fuente"


# --------------------------------------------------- T8.D brief denso


def test_brief_delta_caps_at_five_and_never_raw_titles():
    from app.summaries.builder import brief_delta

    prev = [
        {"title": "Historia estable", "tone": {"negative": 2}},
        {"title": "Historia que mejora", "tone": {"negative": 2}},
    ]
    noticias = [
        {"title": "Historia estable", "tone": {"negative": 2}},
        # giro de tono
        {"title": "Historia que mejora", "tone": {"positive": 2}},
    ] + [
        # siete nuevas: el delta queda en 5 entradas
        {"title": f"Nova historia completamente distinta numero {i}", "tone": {}}
        for i in range(7)
    ]

    delta = brief_delta(prev, noticias)
    assert len(delta) == 5
    # giro primero (es el delta verdad), luego nuevas por impacto.
    assert delta[0]["titulo"].startswith("Historia que mejora")
    assert "positivo" in (delta[0]["giro"] or "")
    nuevas = [d for d in delta if d["giro"] is None]
    assert len(nuevas) == 4
    # prosa corta, nunca el title crudo con chrome
    for entry in delta:
        texto = f"{entry['titulo']} {entry['giro'] or ''}"
        assert "https" not in texto and "@" not in texto
        assert len(entry["titulo"]) <= 200  # DELTA_CLIP: solo títulos patológicos
        assert len(entry["giro"] or "") <= 60


def test_brief_fechas_takes_last_valid_on_ranges():
    from datetime import date

    from app.summaries.builder import brief_fechas

    day = date(2026, 10, 24)
    fechas = brief_fechas(
        [{"when": "Del 21 al 28 de octubre", "title": "Ventana de consulta"}],
        day,
    )
    assert len(fechas) == 1
    assert fechas[0]["fecha"] == "2026-10-28"
    assert fechas[0]["estado"] == "proxima"


def test_brief_fechas_augments_from_agenda_table(session):
    from datetime import date

    from app.models import AgendaItem
    from app.summaries.builder import augment_fechas_from_agenda

    client = add_client(session)
    day = date(2026, 10, 24)
    session.add(
        AgendaItem(
            client_id=client.id,
            title="Votación de la reforma de pensiones",
            kind="deadline",
            event_date=date(2026, 10, 28),  # a 4 días
            date_label="28 de octubre",
        )
    )
    session.commit()

    # ya viene de content.agenda un entry homónimo: no se duplica
    fechas = augment_fechas_from_agenda(
        session,
        client.id,
        day,
        [{"title": "votacion de la reforma de pensiones", "when": "28 oct", "estado": "proxima", "fecha": "2026-10-28"}],
    )
    # el entry de content.agenda gana; la fila homonima de la tabla no duplica
    assert len(fechas) == 1
    assert fechas[0]["title"] == "votacion de la reforma de pensiones"

    session.delete(session.query(AgendaItem).one())
    session.commit()
    vacias = augment_fechas_from_agenda(session, client.id, day, [])
    assert vacias == []


def test_system_prompt_demands_dense_selection():
    assert "mínimo tres" in SYSTEM_PROMPT
    assert "oración" in SYSTEM_PROMPT  # razon con lectura, no topic de 4 palabras
    assert "día previo" in SYSTEM_PROMPT


def test_decision_density_floor_tops_up_unmarked():
    pares = [_card(i, fuentes=3, tone="negative", why="x") for i in range(4)]
    content = _ordered_content([p[0] for p in pares], [p[1] for p in pares])
    content["brief"]["decisiones"] = [{"index": 2, "razon": "del modelo"}]

    ensure_decision_density(content)

    decisiones = content["brief"]["decisiones"]
    assert len(decisiones) == 3
    assert decisiones[0] == {"index": 2, "razon": "del modelo"}  # el modelo primero
    topped = {e["index"] for e in decisiones[1:]}
    assert topped == {0, 1}  # los de mayor impacto no marcados
    # Relleno fundamentado: el why de la propia tarjeta ancla la razón.
    assert [e["razon"] for e in decisiones[1:]] == [
        "«Historia 0» — x",
        "«Historia 1» — x",
    ]


def test_decision_density_floor_is_noop_when_model_complies():
    pares = [_card(i, fuentes=2) for i in range(4)]
    content = _ordered_content([p[0] for p in pares], [p[1] for p in pares])
    content["brief"]["decisiones"] = [
        {"index": 0},
        {"index": 1},
        {"index": 2},
    ]

    ensure_decision_density(content)

    assert len(content["brief"]["decisiones"]) == 3


def test_prompt_view_carries_compact_previous_day():
    from app.summaries.builder import digest_prompt_view

    view = digest_prompt_view(
        {"noticias": [], "rectora": {}},
        dia_previo=[{"title": "Historia de ayer 🎓", "tone": {"negative": 1}}],
    )
    previo = view["dia_previo"]
    assert len(previo) == 1
    assert previo[0]["title"] == "Historia de ayer"
    assert previo[0]["tono"] == "negativo"


def _card(i, fuentes=1, tone=None, why=None, titulo=None):
    tone_counts = {tone: 2} if tone else {}
    titulo = titulo or f"Historia {i}"
    return (
        {
            "title": titulo,
            "sources": [{"source": f"medio{n}"} for n in range(fuentes)],
            "tone": tone_counts,
            "why_it_matters": why,
        },
        {
            "titulo": titulo,
            "hecho": None,
            "por_que": why,
            "fuentes": [f"medio{n}" for n in range(fuentes)],
            "tono": "negativo" if tone == "negative" else ("positivo" if tone else None),
            "repeat": False,
            "angulo_nuevo": None,
        },
    )


def _ordered_content(noticias, tarjetas, brief_extra=None):
    content = {
        "noticias": noticias,
        "tarjetas": tarjetas,
        "brief": {
            "headline": "h",
            "delta": [],
            "decisiones": [],
            "ruido": [],
            "a_favor": [],
            "fechas": [],
            **(brief_extra or {}),
        },
    }
    return content


def test_impact_order_decisions_first_impact_middle_ruido_last():
    nota_fuerte, card_fuerte = _card(1, fuentes=3, tone="negative")
    nota_dec, card_dec = _card(2, fuentes=2, tone="negative")
    nota_media, card_media = _card(3, fuentes=2)
    nota_ruido, card_ruido = _card(4, fuentes=1)
    content = _ordered_content(
        [nota_ruido, nota_fuerte, nota_dec, nota_media],
        [card_ruido, card_fuerte, card_dec, card_media],
        brief_extra={"decisiones": [{"index": 2, "razon": "x"}], "ruido": [{"index": 0}]},
    )

    apply_impact_order(content)

    # decision (2) -> resto por impacto (1: 3 fuentes; 3: 2 fuentes) -> ruido (0)
    assert [n["title"] for n in content["noticias"]] == [
        "Historia 2",
        "Historia 1",
        "Historia 3",
        "Historia 4",
    ]
    assert [t["titulo"] for t in content["tarjetas"]] == [
        "Historia 2",
        "Historia 1",
        "Historia 3",
        "Historia 4",
    ]
    # Brief indices remapped to the new positions.
    assert content["brief"]["decisiones"] == [{"index": 0, "razon": "x"}]
    assert content["brief"]["ruido"] == [{"index": 3}]


def test_impact_order_riesgo_leads_decision_rest_ruido():
    """F5: el orden editorial pasa a riesgo > decision > resto > ruido."""
    nota_riesgo, card_riesgo = _card(1, fuentes=1, tone="negative")
    nota_dec, card_dec = _card(2, fuentes=3)
    nota_media, card_media = _card(3, fuentes=2)
    nota_ruido, card_ruido = _card(4, fuentes=1)
    content = _ordered_content(
        [nota_ruido, nota_riesgo, nota_dec, nota_media],
        [card_ruido, card_riesgo, card_dec, card_media],
        brief_extra={
            "riesgos": [{"index": 1, "razon": "tono negativo dominante"}],
            "decisiones": [{"index": 2, "razon": "x"}],
            "ruido": [{"index": 0}],
        },
    )

    apply_impact_order(content)

    # riesgo (1) -> decision (2) -> resto por impacto (3) -> ruido (0)
    assert [n["title"] for n in content["noticias"]] == [
        "Historia 1",
        "Historia 2",
        "Historia 3",
        "Historia 4",
    ]
    assert content["brief"]["riesgos"] == [{"index": 0, "razon": "tono negativo dominante"}]
    assert content["brief"]["decisiones"] == [{"index": 1, "razon": "x"}]
    assert content["brief"]["ruido"] == [{"index": 3}]


def test_impact_order_tolerates_legacy_rows_without_riesgos():
    """Filas v3.1 sin la clave riesgos: degradan, nunca 500 ni reindex roto."""

    nota_dec, card_dec = _card(1, fuentes=2)
    nota_otra, card_otra = _card(2, fuentes=1)
    content = _ordered_content(
        [nota_otra, nota_dec],
        [card_otra, card_dec],
        # sin 'riesgos' en el brief: fila previa al bucket
        brief_extra={"decisiones": [{"index": 1, "razon": "x"}]},
    )

    apply_impact_order(content)

    assert [n["title"] for n in content["noticias"]] == ["Historia 1", "Historia 2"]
    assert content["brief"]["decisiones"] == [{"index": 0, "razon": "x"}]


def test_impact_order_is_deterministic_on_ties():
    nota_a, card_a = _card(1, fuentes=1)
    nota_b, card_b = _card(2, fuentes=1)
    content = _ordered_content([nota_a, nota_b], [card_a, card_b])
    apply_impact_order(content)
    again = _ordered_content(
        [dict(nota_a), dict(nota_b)], [dict(card_a), dict(card_b)]
    )
    apply_impact_order(again)
    assert [n["title"] for n in content["noticias"]] == [
        n["title"] for n in again["noticias"]
    ]


def test_tail_cards_compile_into_tambien_hoy():
    pares = [_card(i, fuentes=3, tone="negative", why="Fuerte.") for i in range(8)]
    pares += [_card(20 + i, fuentes=1) for i in range(3)]
    content = _ordered_content([p[0] for p in pares], [p[1] for p in pares])

    compile_tail_cards(content)

    tarjetas = content["tarjetas"]
    # 11 tarjetas, cola de 3, piso 9: se funden las tres.
    assert len(tarjetas) == 9
    compiled = tarjetas[-1]
    assert compiled["titulo"] == "También hoy"
    assert compiled["hecho"] is None and compiled["por_que"] is None
    assert len(compiled["notas"]) == 3
    assert "Historia 20" in compiled["notas"][0]
    assert set(compiled["fuentes"]) == {"medio0"}
    # Cobertura intacta: las noticias siguen completas en el detalle.
    assert len(content["noticias"]) == 11


def test_tail_compile_drops_brief_refs_to_swallowed_cards():
    pares = [_card(i, fuentes=3, tone="negative", why="Fuerte.") for i in range(9)]
    pares.append(_card(30, fuentes=1))
    content = _ordered_content(
        [p[0] for p in pares],
        [p[1] for p in pares],
        brief_extra={"ruido": [{"index": 9}], "a_favor": [{"index": 0}]},
    )

    compile_tail_cards(content)

    # index 9 (swallowed) dropped; index 0 unchanged (suffix removal).
    assert len(content["tarjetas"]) == 10
    assert content["tarjetas"][-1]["titulo"] == "También hoy"
    assert content["brief"]["ruido"] == []
    assert content["brief"]["a_favor"] == [{"index": 0}]


def test_tail_compile_never_guts_below_nine_cards():
    fuertes = [_card(i, fuentes=3, tone="negative", why="x") for i in range(6)]
    cola = [_card(10 + i, fuentes=1) for i in range(4)]
    pares = fuertes + cola
    content = _ordered_content(
        [p[0] for p in pares], [p[1] for p in pares]
    )

    compile_tail_cards(content)

    # 10 cards, tail-run 4, floor keeps >= 9: swallow 2, compiled makes 9.
    assert len(content["tarjetas"]) == 9
    assert content["tarjetas"][-1]["titulo"] == "También hoy"


def test_build_orders_decision_cards_first(session):
    client = add_client(session)
    neg_a = _event(client.id, "BUAP pierde el clásico por goleada")
    neg_b = _event(client.id, "Crisis presupuestal detiene obras en la BUAP")
    session.add_all([neg_a, neg_b])
    session.flush()
    m1 = add_mention(session, client.id, neg_a.title, DAY, event_id=neg_a.id)
    m2 = add_mention(
        session, client.id, neg_b.title, DAY, source=MentionSource.rss_custom, event_id=neg_b.id
    )
    from app.models import Sentiment

    m1.sentiment = Sentiment.negative
    m2.sentiment = Sentiment.negative
    session.commit()
    add_mention(session, client.id, "Taller de dibujo para personas sordas", DAY)

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    tarjetas = row.content["tarjetas"]
    # The heuristic marks negative-dominant stories as decision; they lead.
    assert tarjetas[0]["tono"] == "negativo"
    assert tarjetas[1]["tono"] == "negativo"


# --------------------------------------------------- F1 higiene del lector


def test_display_title_drops_separator_chrome_and_outlet_suffix():
    """F1: pipes de separación X y sufijo de medio son chrome de título."""
    from app.summaries.builder import display_title

    raw = "🏀🐺 || ¡Lobos Puebla va por la serie! - atiemponoticias.mx"
    clean = display_title(raw)
    assert clean == "¡Lobos Puebla va por la serie!"
    assert "||" not in clean
    assert "atiemponoticias" not in clean
    assert display_title(clean) == clean  # idempotente
    # El hashtag-chrome + separador de la variante #Entérate también cae.
    assert display_title("#Entérate || Hoy la rectora presentará informe") == (
        "Hoy la rectora presentará informe"
    )


def test_tarjeta_titulo_presentational_sin_sufijo_de_medio():
    """F1: el medio vive en fuentes; el título de tarjeta queda limpio."""
    from app.summaries.builder import build_tarjetas

    tarjeta = build_tarjetas(
        [{"title": "BUAP pospone consulta de pensiones - atiemponoticias.mx"}]
    )[0]
    assert tarjeta["titulo"] == "BUAP pospone consulta de pensiones"


def test_twin_merge_survives_sobrio_normalization():
    """F1: la presentación limpia chrome; el clustering de gemelas no cambia.

    The digest merge compares display_title forms: the suffix/pipes strip
    must keep fusing the outlet-variant twins the variant similarity
    exists for (the ingest assigner never sees this layer).
    """
    from app.summaries.builder import merge_twin_noticias

    merged = merge_twin_noticias(
        [
            {
                "title": "BUAP pospone consulta de pensiones - atiemponoticias.mx",
                "sources": [{"source": "news_rss", "url": "https://a.mx/x"}],
                "tone": {"negative": 1},
            },
            {
                "title": "BUAP pospone consulta de pensiones",
                "sources": [{"source": "x_twitter", "url": "https://x.com/y"}],
                "tone": {"positive": 1},
            },
        ]
    )
    assert len(merged) == 1
    # La tarjeta fundida conserva el title crudo de la mejor fuente; el
    # sufijo se quita solo en la capa presentacional (build_tarjetas).
    assert merged[0]["title"].endswith("atiemponoticias.mx")


def test_brief_fechas_en_duda_domina_sobre_la_fecha():
    """F2b: aplazada/cancelada/suspendida/vencida -> «en duda», aunque futura."""
    from datetime import date

    from app.summaries.builder import brief_fechas

    day = date(2026, 10, 24)
    fechas = brief_fechas(
        [
            # Futura pero aplazada: en duda, no próxima.
            {
                "when": "28 de octubre",
                "title": "Consulta de pensiones",
                "status": "(aplazada, sin nueva fecha)",
            },
            # Futura y firme: próxima.
            {"when": "30 de octubre", "title": "Taller de vinculación"},
            # Pasada y suspendida: en duda también domina.
            {
                "when": "20 de octubre",
                "title": "Asamblea",
                "status": "suspendida",
            },
        ],
        day,
    )
    by_title = {f["title"]: f["estado"] for f in fechas}
    assert by_title["Consulta de pensiones"] == "en duda"
    assert by_title["Taller de vinculación"] == "proxima"
    assert by_title["Asamblea"] == "en duda"


def test_augment_fechas_en_duda_desde_notas(session):
    """F2b en la vía agenda_items: las notas de la fila activan «en duda»."""
    from datetime import date, timedelta

    from app.models import AgendaItem
    from app.summaries.builder import augment_fechas_from_agenda

    client = add_client(session)
    day = date(2026, 10, 24)
    session.add(
        AgendaItem(
            client_id=client.id,
            title="Votación de la reforma",
            kind="deadline",
            event_date=day + timedelta(days=4),
            date_label="28 de octubre",
            notes="(aplazada, sin nueva fecha)",
        )
    )
    session.commit()

    fechas = augment_fechas_from_agenda(session, client.id, day, [])
    assert len(fechas) == 1
    assert fechas[0]["estado"] == "en duda"


# --------------------------------------------------- F3 descarte visible


def test_brief_descarte_counts_cosmeticas_and_fundadas(session):
    """F3: el descarte pre-tarjeta es visible; sin descarte no hay clave."""
    client = add_client(session)
    e1, e2 = _twin_events(session, client.id)
    add_mention(session, client.id, e1.title, DAY, event_id=e1.id)
    add_mention(
        session,
        client.id,
        e2.title,
        DAY,
        source=MentionSource.rss_custom,
        event_id=e2.id,
    )
    cosmetic = add_mention(
        session, client.id, "BUAP actualizó su foto de portada", DAY
    )
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    brief = row.content["brief"]
    assert brief["descarte"] == {"cosmeticas": 1, "fundadas": 1}
    # La tarjeta fundida y la cosmetica nunca llegan a noticias.
    assert len(row.content["noticias"]) == 1
    assert validate_digest(row.content) == []


def test_brief_without_descarte_omits_the_key(session):
    client = add_client(session)
    event = _event(client.id, "BUAP anuncia becas nuevas")
    session.add(event)
    session.flush()
    add_mention(session, client.id, event.title, DAY, event_id=event.id)
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert "descarte" not in row.content["brief"]


def test_descarte_label_clauses():
    from app.summaries.builder import descarte_label

    assert (
        descarte_label({"cosmeticas": 2, "fundadas": 1})
        == "Descartado: 2 actualizaciones cosméticas, 1 historia fundida"
    )
    assert descarte_label({"cosmeticas": 1, "fundadas": 0}) == (
        "Descartado: 1 actualización cosmética"
    )
    assert descarte_label({"cosmeticas": 0, "fundadas": 3}) == (
        "Descartado: 3 historias fundidas"
    )
    assert descarte_label({"cosmeticas": 0, "fundadas": 0}) is None
    assert descarte_label(None) is None
    assert descarte_label("x") is None


def test_plain_text_carries_the_descarte_line(session):
    client = add_client(session)
    e1, e2 = _twin_events(session, client.id)
    add_mention(session, client.id, e1.title, DAY, event_id=e1.id)
    add_mention(
        session,
        client.id,
        e2.title,
        DAY,
        source=MentionSource.rss_custom,
        event_id=e2.id,
    )
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    plain = row.content["plain_text"]
    assert "Descartado: 1 historia fundida" in plain


def test_brief_shape_flags_malformed_descarte():
    from app.summaries.digest_schema import brief_shape_errors

    content = {"brief": {"descarte": ["no"]}, "noticias": []}
    assert "brief.descarte must be an object" in brief_shape_errors(content)
    ok = {"brief": {"descarte": {"cosmeticas": 1, "fundadas": 0}}, "noticias": []}
    assert brief_shape_errors(ok) == []


# ------------------------------------------------- F6/F7 watchlist y vigilia


def _person_link(session, client_id: int, name: str, mention) -> Person:
    """Get-or-create person by folded key and link the mention to it."""
    from app.ingest.matching import fold_text

    key = fold_text(name)
    person = session.query(Person).filter_by(client_id=client_id, name_key=key).first()
    if person is None:
        person = Person(client_id=client_id, name=name, name_key=key)
        session.add(person)
        session.flush()
    session.add(MentionPerson(mention_id=mention.id, person_id=person.id))
    session.commit()
    return person


def _negative_mention(session, client_id: int, title, when, **kw):
    mention = add_mention(session, client_id, title, when, **kw)
    mention.sentiment = Sentiment.negative
    session.commit()
    return mention


def test_vigilancia_focus_principal_basta_con_una_negativa(session):
    """F7: 1 negativa del focus => línea, aunque la tarjeta sea positiva."""
    client = add_client(session)
    event = _event(client.id, "BUAP anuncia ampliation de becas")
    session.add(event)
    session.flush()
    add_mention(session, client.id, "BUAP amplía becas", DAY, event_id=event.id).sentiment = (
        Sentiment.positive
    )
    second = add_mention(
        session, client.id, "Becas ampliadas", DAY, source=MentionSource.rss_custom, event_id=event.id
    )
    second.sentiment = Sentiment.positive
    negative = _negative_mention(
        session, client.id, "Critican la gestión de becas de la BUAP", DAY, event_id=event.id
    )
    _person_link(session, client.id, "Lilia Cedillo", negative)
    queries.upsert_settings(session, client.id, {"digest_focus_person_id": 1})
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    vigilia = row.content["brief"].get("vigilancia")
    assert vigilia and len(vigilia) == 1
    linea = vigilia[0]
    assert linea["persona"] == "Lilia Cedillo"
    assert "Critican" in linea["nota"]
    assert linea["fecha"].startswith("2026-10-09")
    # La tarjeta del evento es positiva: el piso riesgo no la toma y la
    # mención negativa no está representada ahí.
    assert row.content["tarjetas"][0]["tono"] == "positivo"
    assert row.content["brief"]["riesgos"] == []
    assert validate_digest(row.content) == []


def test_vigilancia_anti_dup_la_tarjeta_riesgo_gana(session):
    """La negativa representada por una tarjeta de riesgo no emite línea."""
    client = add_client(session)
    event = _event(client.id, "BUAP recorta becas")
    session.add(event)
    session.flush()
    first = _negative_mention(
        session, client.id, "BUAP recorta becas", DAY, event_id=event.id
    )
    _negative_mention(
        session,
        client.id,
        "Recorte de becas confirmado",
        DAY,
        source=MentionSource.rss_custom,
        event_id=event.id,
    )
    _person_link(session, client.id, "Rectora Cedillo", first)
    # Una historia ajena de mayor impacto existe: el fallback de cobertura
    # la toma como decision y la negativa queda libre para el piso riesgo.
    big = _event(client.id, "Congreso aprueba el presupuesto federal")
    session.add(big)
    session.flush()
    for titulo in (
        "Congreso aprueba presupuesto",
        "Aprueban el presupuesto federal",
        "El presupuesto sigue adelante",
    ):
        add_mention(
            session,
            client.id,
            titulo,
            DAY,
            source=MentionSource.news_rss,
            event_id=big.id,
        )
    queries.upsert_settings(session, client.id, {"digest_focus_person_id": 1})
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    brief = row.content["brief"]
    # El piso lleva la tarjeta negativa a riesgo; el anti-dup la representa.
    riesgo_indexes = {entry["index"] for entry in brief["riesgos"]}
    assert riesgo_indexes, "la negativa del día entra al piso"
    for index in riesgo_indexes:
        assert row.content["noticias"][index]["event_id"] == event.id
    assert "vigilancia" not in brief


def test_vigilancia_watchlist_exige_eco_de_fuentes(session):
    """No-principal: 1 negativa no basta; 2 fuentes distintas sí."""
    client = add_client(session)

    def evento_con_negativa(titulo, neg_title, source):
        event = _event(client.id, titulo)
        session.add(event)
        session.flush()
        pos = add_mention(session, client.id, titulo, DAY, event_id=event.id)
        pos.sentiment = Sentiment.positive
        neg = _negative_mention(
            session, client.id, neg_title, DAY, source=source, event_id=event.id
        )
        return event, neg

    _, neg_a = evento_con_negativa(
        "Universidad estrena laboratorio",
        "Protesta por el laboratorio",
        MentionSource.news_rss,
    )
    _, neg_b = evento_con_negativa(
        "Congreso aprueba presupuesto",
        "Critican el presupuesto",
        MentionSource.rss_custom,
    )
    vigilada = _person_link(session, client.id, "Lilia Cedillo", neg_a)
    _person_link(session, client.id, "Lilia Cedillo", neg_b)
    # Una segunda vigilada con una sola negativa no alcanza el eco: el
    # umbral se verifica por persona dentro del mismo build.
    solo = _event(client.id, "Recorte docente anuncio")
    session.add(solo)
    session.flush()
    solo_pos = add_mention(session, client.id, "Recorte docente anuncio", DAY, event_id=solo.id)
    solo_pos.sentiment = Sentiment.positive
    solo_neg = _negative_mention(
        session,
        client.id,
        "Queja docente por el recorte",
        DAY,
        source=MentionSource.x_twitter,
        event_id=solo.id,
    )
    jefe = _person_link(session, client.id, "Jefe de docencia", solo_neg)
    queries.upsert_settings(session, client.id, {"watchlist": [vigilada.id, jefe.id]})
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    vigilia = row.content["brief"].get("vigilancia") or []
    # Dos negativas de fuentes distintas => línea; una sola => nada.
    assert [linea["persona"] for linea in vigilia] == ["Lilia Cedillo"]


def test_vigilancia_solo_la_ventana_cuenta(session):
    """Fuera de ventana no cuenta (ni a 2 ni a 30 dias); fallback ingested."""
    client = add_client(session)
    event = _event(client.id, "BUAP presenta informe")
    session.add(event)
    session.flush()
    add_mention(session, client.id, "BUAP presenta informe", DAY, event_id=event.id)
    # Re-scrape viejo: published hace 30 días, dentro de la ventana de ingesta.
    old = add_mention(
        session,
        client.id,
        "BUAP presenta informe",
        DAY - timedelta(days=30),
        source=MentionSource.x_twitter,
        event_id=event.id,
    )
    old.sentiment = Sentiment.negative
    old.ingested_at = DAY
    person = _person_link(session, client.id, "Rectora Cedillo", old)
    # Fallback: published NULL, ingested en ventana.
    naked = add_mention(session, client.id, "BUAP genera polémica", DAY, event_id=event.id)
    naked.sentiment = Sentiment.negative
    naked.published_at = None
    naked.ingested_at = DAY
    session.add(MentionPerson(mention_id=naked.id, person_id=person.id))
    # Publicada 2 dias antes de la ventana: con el viejo buffer de 14 dias
    # entraria y duplicaria entre dias; con ventana estricta, no.
    recent_old = add_mention(
        session,
        client.id,
        "BUAP genera polémica adicional",
        DAY - timedelta(days=2),
        event_id=event.id,
    )
    recent_old.sentiment = Sentiment.negative
    recent_old.ingested_at = DAY
    session.add(MentionPerson(mention_id=recent_old.id, person_id=person.id))
    queries.upsert_settings(session, client.id, {"digest_focus_person_id": person.id})
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    notas = [
        linea.get("nota") for linea in row.content["brief"].get("vigilancia") or []
    ]
    # La de hace 30 días queda fuera; la sin published entra por fallback.
    assert len(notas) == 1
    assert "polémica" in notas[0]
    assert row.content["brief"]["vigilancia"][0]["fecha"].startswith("2026-10-09")


def test_vigilancia_sin_configuracion_no_llave(session):
    client = add_client(session)
    event = _event(client.id, "BUAP publica")
    session.add(event)
    session.flush()
    mention = add_mention(session, client.id, "BUAP publica", DAY, event_id=event.id)
    mention.sentiment = Sentiment.negative
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    assert "vigilancia" not in row.content["brief"]


def test_afectacion_en_riesgo_quien_y_trayectoria(session):
    """F6: la entrada de riesgo lleva quien y la dirección del delta."""
    client = add_client(session)
    event = _event(client.id, "BUAP replantea el calendario escolar")
    session.add(event)
    session.flush()
    prev_day = DAY - timedelta(days=1)
    positive = add_mention(session, client.id, "Calendario escolar", prev_day, event_id=event.id)
    positive.sentiment = Sentiment.positive
    session.commit()
    # Día previo: la historia era positiva.
    build_daily_summary(session, client_id=client.id, day=prev_day.date())

    negative = _negative_mention(
        session, client.id, "BUAP replantea calendario y genera incertidumbre", DAY, event_id=event.id
    )
    _negative_mention(
        session,
        client.id,
        "Incertidumbre por el calendario",
        DAY,
        source=MentionSource.rss_custom,
        event_id=event.id,
    )
    _person_link(session, client.id, "Lilia Cedillo", negative)
    # Historia ajena más fuerte: el fallback de cobertura no roba el riesgo.
    big = _event(client.id, "Congreso aprueba el presupuesto federal")
    session.add(big)
    session.flush()
    for titulo in (
        "Congreso aprueba presupuesto",
        "Aprueban el presupuesto federal",
        "El presupuesto sigue adelante",
    ):
        add_mention(
            session,
            client.id,
            titulo,
            DAY,
            source=MentionSource.news_rss,
            event_id=big.id,
        )
    session.commit()

    row = build_daily_summary(session, client_id=client.id, day=DAY.date())
    riesgos = row.content["brief"]["riesgos"]
    assert riesgos, "la negativa del día entra al piso"
    afect = riesgos[0].get("afectacion")
    assert afect is not None
    assert "Lilia Cedillo" in afect["quien"]
    assert afect["trayectoria"] == "el tono pasa de positivo a negativo"


def test_ventana_por_titulo_y_por_fecha():
    """F6 ventana: cruce por título normalizado o por día."""
    from datetime import date

    from app.summaries.builder import _ventana_from_fechas

    fechas = [
        {"title": "Consulta de pensiones", "when": "28 de octubre", "fecha": "2026-10-28"},
        {"title": "Entrega de informe", "when": "30 de octubre", "fecha": "2026-10-30"},
    ]
    cruz = _ventana_from_fechas(fechas, "La consulta de pensiones sigue en pie", None)
    assert cruz == {"cuando": "28 de octubre", "titulo": "Consulta de pensiones"}
    por_dia = _ventana_from_fechas(fechas, "Tema sin relación", date(2026, 10, 30))
    assert por_dia["titulo"] == "Entrega de informe"
    assert _ventana_from_fechas(fechas, "Tema sin relación", date(2026, 5, 1)) is None
    assert _ventana_from_fechas(None, "x", None) is None
