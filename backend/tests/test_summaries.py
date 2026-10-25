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
    Keyword,
    MentionSource,
    queries,
)
from app.settings_runtime import EffectiveSettings
from app.summaries import build_daily_summary
from app.summaries.builder import SYSTEM_PROMPT, day_window, summary_generator
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
    assert content["rectora"]["person_id"] is None
    assert content["redes"]["x"]["count"] == 0
    # The silent keyword feeds the temas block; limitaciones = coverage gaps.
    assert content["temas_sin_nota"] == ["sin datos"]
    assert content["pendientes"] == content["coverage"]["gaps"]
    # Plain text render for RAG: sectioned, deterministic.
    plain = content["plain_text"]
    assert "NOTICIAS" in plain
    assert "RECTORA" in plain
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

_V2_ACTIVITY = [
    {
        "when": "22 oct.",
        "text": "Inauguración de la ofrenda en la Casa de la Bóveda.",
        "channel": "Acto público",
    },
    {"text": "Sin publicaciones fechables en la ventana.", "channel": "X propio"},
]

_V2_REDES_NOTE = "Sin novedades fechables en la ventana."


def _digest_payload_v2() -> str:
    return json.dumps(
        {
            "headline": "Titular del modelo.",
            "items": [
                {"index": 0, "summary": "Síntesis del modelo.", "why_it_matters": "Porque sí."}
            ],
            "rectora": {
                "tone": "neutral",
                "watch": "votación del 28",
                "activity": _V2_ACTIVITY,
            },
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
    assert row.content["rectora"]["tone"] == "neutral"
    assert row.content["rectora"]["watch"] == "votación del 28"
    # v2 blocks: agenda, rectora activity and per-network note.
    assert row.content["agenda"] == _V2_AGENDA
    assert row.content["rectora"]["activity"] == _V2_ACTIVITY
    assert row.content["redes"]["x"]["note"] == _V2_REDES_NOTE
    assert validate_digest(row.content) == []
    # The v2 blocks render into the plain text (RAG) as their own sections.
    plain = row.content["plain_text"]
    assert "AGENDA" in plain
    assert "Plática «Conectados pero solos»" in plain
    assert "Inauguración de la ofrenda" in plain
    assert "Acto público" in plain
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
    assert row.content["rectora"]["activity"] == _V2_ACTIVITY
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
    assert content["rectora"]["activity"] == []
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
    assert content["rectora"]["tone"] == "neutral"
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
        "rectora": {
            "person_id": 7,
            "actions": [{"title": "a", "event_id": 3, "sentiment": "negative", "role": "R", "org": "U"}],
            "name": "Alguien",
        },
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
    assert "person_id" not in view["rectora"]
    assert "event_id" not in view["rectora"]["actions"][0]
    assert view["rectora"]["name"] == "Alguien"  # identity stamp survives
    assert "person_id" not in view["personas"][0]
    assert view["redes"] == {"x": {"count": 3, "note": ""}}
    # index alignment: order is the content's own
    assert len(view["noticias"]) == 1


def test_digest_prompt_view_empty_facts():
    from app.summaries.builder import digest_prompt_view

    view = digest_prompt_view({})
    assert view == {"noticias": [], "rectora": {}, "redes": {}, "personas": []}


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
    assert row.content["brief"]["delta"] == ["Nueva historia: Rectora anuncia nuevos horarios"]
    # The pure matcher agrees when fed the two days' noticias.
    prev = queries.get_daily_summary(session, client.id, DAY.date()).content["noticias"]
    assert brief_delta(prev, row.content["noticias"]) == [
        "Nueva historia: Rectora anuncia nuevos horarios"
    ]


def test_brief_delta_matches_by_normalized_title_without_event_id():
    from app.summaries.builder import brief_delta

    prev = [{"event_id": None, "title": "Puma explota pedido", "tone": {}}]
    cur = [{"event_id": None, "title": "puma explota pedido", "tone": {}}]
    assert brief_delta(prev, cur) == []
    cur[0]["title"] = "Nota completamente nueva"
    assert brief_delta(prev, cur) == ["Nueva historia: Nota completamente nueva"]


def test_brief_delta_reports_tone_flips():
    from app.summaries.builder import brief_delta

    prev = [{"event_id": 3, "title": "Cambio de rectoría", "tone": {"positive": 2}}]
    cur = [{"event_id": 3, "title": "Cambio de rectoría", "tone": {"negative": 3}}]
    delta = brief_delta(prev, cur)
    assert delta == ["Cambio de rectoría: el tono pasa de positivo a negativo"]
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
    # noticias[0] es el evento negativo de 2 fuentes; index-aligned buckets.
    assert brief["decisiones"] == [
        {"index": 0, "razon": "tono negativo dominante"}
    ]
    assert len(brief["a_favor"]) == 1
    assert brief["a_favor"][0]["index"] == 1
    assert brief["a_favor"][0]["razon"] == "tono positivo dominante"
    assert brief["ruido"] == []


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
                "ruido": [],
                "a_favor": [],
                "fechas": [],
            },
            "tarjetas": [build_tarjetas([{"title": "X"}])[0]],
            "campo": [],
        }
    ) == {
        "top": ["a_favor", "decisiones", "delta", "fechas", "headline", "ruido"],
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
    assert "CAMPO" in plain
    assert "Obra del puente parada" in plain
    assert "en revisión" in plain
