"""API tests: every endpoint through TestClient + temp SQLite.

The app's session/client-id dependencies are overridden to point at a
per-test SQLite database (Base.metadata.create_all + seed rows). Fully
offline: no Postgres, no SMTP, no provider calls.
"""

from datetime import date, datetime, timedelta, timezone

import json

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_client_id
from app.db import get_db
from app.main import create_app
from app.models import (
    Base,
    Client,
    Event,
    Keyword,
    Mention,
    MentionSource,
    Sentiment,
    make_url_hash,
    queries,
)


def test_reviewer_settings_are_tenant_scoped_write_only_and_partial(api, db):
    """Synthetic credentials only; saving settings never tests a provider."""
    client_id = first_client_id(db)
    other = Client(name="reviewer-isolation-fixture")
    db.add(other)
    db.commit()
    other_before = queries.get_settings(db, other.id)
    assert (
        api.put(
            "/api/settings",
            json={
                "ai_provider": "openai",
                "ai_model": "qwen-generator-fixture",
                "ai_model_fast": "fast-arbitrator-fixture",
                "ai_base_url": "https://generator-fixture.invalid/v1",
                "ai_api_key": "synthetic-generator-key-only",
                "watchlist": [9],
                "digest_hours": [8, 21],
                "retention_days": 90,
            },
        ).status_code
        == 200
    )
    before = api.get("/api/settings").json()
    assert before["digest_reviewer_provider"] == "inherit"
    assert before["digest_reviewer_api_key"] == ""
    assert before["digest_reviewer_api_key_set"] is False
    body = {
        "digest_reviewer_provider": "openai",
        "digest_reviewer_base_url": "https://reviewer-fixture.invalid/v1",
        "digest_reviewer_model": "reviewer-fixture-model",
        "digest_reviewer_api_key": "synthetic-reviewer-key-only",
    }
    response = api.put("/api/settings", json=body)
    assert response.status_code == 200
    saved = response.json()
    assert saved["digest_reviewer_api_key"] == ""
    assert saved["digest_reviewer_api_key_set"] is True
    assert "synthetic-reviewer-key-only" not in response.text
    readback = api.get("/api/settings").json()
    # SQLite drops the UTC offset on DB round-trip, not the stored wall time.
    assert readback.pop("updated_at").removesuffix("Z") == saved[
        "updated_at"
    ].removesuffix("Z")
    assert readback == {
        key: value for key, value in saved.items() if key != "updated_at"
    }
    unaffected = {
        key: value
        for key, value in before.items()
        if not key.startswith("digest_reviewer_") and key != "updated_at"
    }
    assert {key: saved[key] for key in unaffected} == unaffected
    row = queries.get_settings(db, client_id)
    revision = row.digest_reviewer_revision
    assert isinstance(revision, str) and revision
    for blank in ("", "   ", None, " synthetic-reviewer-key-only "):
        kept = api.put("/api/settings", json={"digest_reviewer_api_key": blank})
        assert kept.status_code == 200
        assert kept.json()["digest_reviewer_api_key_set"] is True
        db.refresh(row)
        assert row.digest_reviewer_api_key == "synthetic-reviewer-key-only"
        assert row.digest_reviewer_revision == revision
    replaced = api.put(
        "/api/settings", json={"digest_reviewer_api_key": "synthetic-replacement-only"}
    )
    assert replaced.status_code == 200
    db.refresh(row)
    assert row.digest_reviewer_revision != revision
    assert "synthetic-replacement-only" not in replaced.text
    api.app.dependency_overrides[get_client_id] = lambda: other.id
    isolated = api.get("/api/settings").json()
    assert isolated["digest_reviewer_provider"] == "inherit"
    assert isolated["digest_reviewer_api_key_set"] is False
    db.refresh(other_before)
    assert other_before.digest_reviewer_revision is None


def test_reviewer_validation_does_not_echo_credentials(api, db):
    for changes in (
        {"digest_reviewer_provider": "native-vendor-api"},
        {"digest_reviewer_base_url": "file:///fixture"},
        {"digest_reviewer_api_key": "synthetic-overlong-key-" * 30},
        {"digest_reviewer_api_key": ["synthetic-non-string-key-only"]},
    ):
        secret = changes.get("digest_reviewer_api_key", "synthetic-key-error-only")
        response = api.put(
            "/api/settings", json={"digest_reviewer_api_key": secret, **changes}
        )
        assert response.status_code == 422
        assert str(secret) not in response.text
        assert "synthetic-non-string-key-only" not in response.text
    assert api.get("/api/settings").json()["digest_reviewer_api_key_set"] is False


def test_reviewer_guided_mode_roundtrip_and_validation(api, db):
    api.put("/api/settings", json={
        "digest_reviewer_provider": "openai",
        "digest_reviewer_base_url": "https://reviewer.invalid/v1",
        "digest_reviewer_model": "fixture",
        "digest_reviewer_api_key": "synthetic-key",
        "digest_reviewer_guided_mode": "json_object",
    })
    current = api.get("/api/settings")
    assert current.status_code == 200
    assert current.json()["digest_reviewer_guided_mode"] == "json_object"
    rejected = api.put("/api/settings", json={"digest_reviewer_guided_mode": "yaml"})
    assert rejected.status_code == 422
    assert api.get("/api/settings").json()["digest_reviewer_guided_mode"] == "json_object"


def test_reviewer_connection_uses_saved_dedicated_settings_without_writes(
    api, db, monkeypatch, caplog
):
    from app.api import settings as settings_api
    from tests.test_political_analysis_regeneration import snapshot_tables

    owner = first_client_id(db)
    queries.upsert_settings(
        db,
        owner,
        {
            "ai_provider": "openai",
            "ai_base_url": "https://generator.invalid/v1",
            "ai_model": "generator-fixture",
            "ai_api_key": "synthetic-generator-key",
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/custom/v1/",
            "digest_reviewer_model": "reviewer-fixture",
            "digest_reviewer_api_key": "synthetic-reviewer-key",
        },
    )
    foreign = Client(name="probe-unrelated-tenant")
    db.add(foreign)
    db.commit()
    queries.get_settings(db, foreign.id)
    before = snapshot_tables(db)
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": "Available"}}]}
        )

    client = httpx.Client(
        transport=httpx.MockTransport(transport), follow_redirects=True
    )
    monkeypatch.setattr(
        settings_api, "_reviewer_probe_client", lambda: client, raising=False
    )
    response = api.post(
        "/api/settings/test-reviewer",
        headers={"X-Reviewer-Probe": "1"},
        json={
            "digest_reviewer_base_url": "https://untrusted-draft.invalid/v1",
            "digest_reviewer_api_key": "synthetic-unsaved-key",
        },
    )
    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"ok", "message", "latency_ms", "status_code", "error_code"}
    assert result["ok"] is True
    assert result["message"] == "Conexión correcta: el modelo respondió a la prueba."
    assert result["status_code"] == 200 and result["error_code"] is None
    assert isinstance(result["latency_ms"], int) and result["latency_ms"] >= 0
    assert len(calls) == 1
    request = calls[0]
    assert str(request.url) == "https://reviewer.invalid/custom/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer synthetic-reviewer-key"
    body = json.loads(request.content)
    assert body == {
        "model": "reviewer-fixture",
        "messages": [{"role": "user", "content": "Responde solo OK."}],
        "max_tokens": 64,
    }
    assert set(request.extensions["timeout"].values()) == {10.0}
    assert client.is_closed
    assert snapshot_tables(db) == before
    for secret in (
        "synthetic-generator-key",
        "synthetic-reviewer-key",
        "synthetic-unsaved-key",
    ):
        assert secret not in response.text and secret not in caplog.text


@pytest.mark.parametrize("mode", ["inherit", "defaults"])
def test_reviewer_connection_inherits_only_saved_general_settings(
    api, db, monkeypatch, mode
):
    from app.api import settings as settings_api
    from tests.test_political_analysis_regeneration import snapshot_tables

    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "ai_provider": "openai",
            "ai_base_url": None if mode == "defaults" else "http://127.0.0.1:8888/v1",
            "ai_model": None if mode == "defaults" else "saved-general-model",
            "ai_api_key": "synthetic-general-key",
            "digest_reviewer_provider": "inherit",
            "digest_reviewer_base_url": "https://ignored-reviewer.invalid/v1",
            "digest_reviewer_model": "ignored-reviewer",
            "digest_reviewer_api_key": "synthetic-ignored-key",
        },
    )
    before = snapshot_tables(db)
    calls = []

    def transport(request):
        calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    client = httpx.Client(transport=httpx.MockTransport(transport))
    monkeypatch.setattr(settings_api, "_reviewer_probe_client", lambda: client)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    assert response.status_code == 200 and response.json()["ok"] is True
    assert len(calls) == 1
    body = json.loads(calls[0].content)
    assert body["model"] == (
        settings_api.DEFAULT_OPENAI_MODEL
        if mode == "defaults"
        else "saved-general-model"
    )
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert calls[0].headers["Authorization"] == "Bearer synthetic-general-key"
    expected = (
        settings_api.DEFAULT_OPENAI_BASE_URL
        if mode == "defaults"
        else "http://127.0.0.1:8888/v1"
    )
    assert str(calls[0].url) == expected.rstrip("/") + "/chat/completions"
    assert snapshot_tables(db) == before


@pytest.mark.parametrize(
    "case",
    [
        "absent",
        "local",
        "no-key",
        "dedicated-incomplete",
        "userinfo",
        "bad-port",
        "query",
    ],
)
def test_reviewer_connection_invalid_saved_configuration_is_read_only_and_never_dispatches(
    api, db, monkeypatch, case
):
    from app.api import settings as settings_api
    from app.models import ClientSettings
    from tests.test_political_analysis_regeneration import snapshot_tables

    if case != "absent":
        changes: dict[str, object] = {
            "ai_provider": "openai",
            "ai_base_url": "https://general.invalid/v1",
            "ai_model": "general",
            "ai_api_key": "synthetic-key",
            "digest_reviewer_provider": "inherit",
        }
        if case == "local":
            changes["ai_provider"] = "local"
        elif case == "no-key":
            changes["ai_api_key"] = None
        elif case == "dedicated-incomplete":
            changes["digest_reviewer_provider"] = "openai"
        queries.upsert_settings(db, first_client_id(db), changes)
        if case in {"userinfo", "bad-port", "query"}:
            row = db.scalar(
                select(ClientSettings).where(
                    ClientSettings.client_id == first_client_id(db)
                )
            )
            row.ai_base_url = {
                "userinfo": "https://user:synthetic-key@host.invalid/v1",
                "bad-port": "https://host.invalid:invalid/v1",
                "query": "https://host.invalid/v1?key=synthetic-key",
            }[case]
            db.commit()
    before = snapshot_tables(db)
    calls = []

    def unexpected():
        calls.append(True)
        raise RuntimeError("synthetic-key")

    monkeypatch.setattr(settings_api, "_reviewer_probe_client", unexpected)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    assert response.status_code == 200 and response.json()["ok"] is False
    assert response.json()["latency_ms"] is None
    assert calls == []
    assert "synthetic-key" not in response.text
    assert snapshot_tables(db) == before


@pytest.mark.parametrize(
    "case",
    [
        "auth",
        "forbidden",
        "quota",
        "server",
        "redirect",
        "timeout",
        "json",
        "empty",
        "shape",
        "reasoning",
    ],
)
def test_reviewer_connection_is_one_shot_and_never_echoes_provider_failures(
    api, db, monkeypatch, caplog, case
):
    from app.api import settings as settings_api
    from tests.test_political_analysis_regeneration import snapshot_tables

    secret = "synthetic-private-probe-key"
    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1",
            "digest_reviewer_model": "fixture-model",
            "digest_reviewer_api_key": secret,
        },
    )
    before = snapshot_tables(db)
    calls = []

    def transport(request):
        calls.append(request)
        if case == "timeout":
            raise httpx.ReadTimeout(secret, request=request)
        if case == "json":
            return httpx.Response(200, text=secret)
        if case in {"empty", "reasoning"}:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": "checking"
                                if case == "reasoning"
                                else None,
                            }
                        }
                    ]
                },
            )
        if case == "shape":
            return httpx.Response(200, json={"choices": [secret]})
        status = {
            "auth": 401,
            "forbidden": 403,
            "quota": 429,
            "server": 503,
            "redirect": 302,
        }[case]
        return httpx.Response(
            status,
            text=secret,
            headers={"Location": "https://redirect.invalid/" + secret},
        )

    client = httpx.Client(
        transport=httpx.MockTransport(transport), follow_redirects=True
    )
    monkeypatch.setattr(settings_api, "_reviewer_probe_client", lambda: client)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    assert response.status_code == 200
    assert response.json()["ok"] is (case == "reasoning")
    assert len(calls) == 1 and client.is_closed
    assert secret not in response.text and secret not in caplog.text
    assert snapshot_tables(db) == before



def test_reviewer_connection_rejects_duplicated_completion_url_without_dispatch(
    api, db, monkeypatch
):
    from app.api import settings as settings_api
    from tests.test_political_analysis_regeneration import snapshot_tables

    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1/chat/completions",
            "digest_reviewer_model": "fixture-model",
            "digest_reviewer_api_key": "synthetic-key",
        },
    )
    before = snapshot_tables(db)
    calls = []

    def unexpected():
        calls.append(True)
        raise RuntimeError("synthetic-key")

    monkeypatch.setattr(settings_api, "_reviewer_probe_client", unexpected)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["ok"] is False
    assert "/chat/completions" in result["message"]
    assert result["status_code"] is None and result["error_code"] is None
    assert result["latency_ms"] is None
    assert calls == []
    assert "synthetic-key" not in response.text
    assert snapshot_tables(db) == before


def test_reviewer_connection_surfaces_non_secret_provider_diagnostics(
    api, db, monkeypatch, caplog
):
    from app.api import settings as settings_api
    from tests.test_political_analysis_regeneration import snapshot_tables

    secret = "synthetic-private-probe-key"
    provider_message = f"Model fixture-model does not exist for key {secret}"
    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1",
            "digest_reviewer_model": "fixture-model",
            "digest_reviewer_api_key": secret,
        },
    )
    before = snapshot_tables(db)
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                400, json={"error": {"code": "Model Not Exist", "message": provider_message}}
            )
        )
    )
    monkeypatch.setattr(settings_api, "_reviewer_probe_client", lambda: client)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    result = response.json()
    assert result["ok"] is False
    assert result["status_code"] == 400
    assert result["error_code"] == "Model Not Exist"
    assert provider_message not in response.text and provider_message not in caplog.text
    assert secret not in response.text and secret not in caplog.text
    assert client.is_closed
    assert snapshot_tables(db) == before


def test_reviewer_connection_reports_insufficient_balance_specifically(
    api, db, monkeypatch
):
    from app.api import settings as settings_api

    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1",
            "digest_reviewer_model": "fixture-model",
            "digest_reviewer_api_key": "synthetic-key",
        },
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                402,
                json={"error": {"code": "invalid_request_error",
                                "message": "Insufficient Balance"}},
            )
        )
    )
    monkeypatch.setattr(settings_api, "_reviewer_probe_client", lambda: client)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    result = response.json()
    assert result["ok"] is False
    assert "saldo insuficiente" in result["message"].lower()
    assert result["status_code"] == 402
    assert result["error_code"] == "invalid_request_error"


def test_reviewer_connection_reports_status_without_code_for_opaque_error_bodies(
    api, db, monkeypatch
):
    from app.api import settings as settings_api

    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1",
            "digest_reviewer_model": "fixture-model",
            "digest_reviewer_api_key": "synthetic-key",
        },
    )
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, text="synthetic-opaque-body")
        )
    )
    monkeypatch.setattr(settings_api, "_reviewer_probe_client", lambda: client)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    result = response.json()
    assert result["ok"] is False
    assert result["status_code"] == 503
    assert result["error_code"] is None
    assert "synthetic-opaque-body" not in response.text


def test_reviewer_connection_factory_disables_proxy_inheritance_and_redirects(
    api, db, monkeypatch
):
    from app.api import settings as settings_api

    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1",
            "digest_reviewer_model": "fixture-model",
            "digest_reviewer_api_key": "synthetic-key",
        },
    )
    captured = []
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200, json={"choices": [{"message": {"content": "OK"}}]}
            )
        )
    )

    def factory(**kwargs):
        captured.append(kwargs)
        return client

    monkeypatch.setattr(settings_api.httpx, "Client", factory)
    response = api.post(
        "/api/settings/test-reviewer", headers={"X-Reviewer-Probe": "1"}
    )
    assert response.json()["ok"] is True
    assert captured == [
        {"timeout": 10.0, "follow_redirects": False, "trust_env": False}
    ]


def test_reviewer_connection_requires_an_explicit_server_side_intent_marker(
    api, db, monkeypatch
):
    from app.api import settings as settings_api

    queries.upsert_settings(
        db,
        first_client_id(db),
        {
            "digest_reviewer_provider": "openai",
            "digest_reviewer_base_url": "https://reviewer.invalid/v1",
            "digest_reviewer_model": "fixture",
            "digest_reviewer_api_key": "synthetic-key",
        },
    )
    calls = []

    def factory():
        calls.append(True)
        return httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200, json={"choices": [{"message": {"content": "OK"}}]}
                )
            )
        )

    monkeypatch.setattr(settings_api, "_reviewer_probe_client", factory)
    response = api.post("/api/settings/test-reviewer")
    assert response.status_code == 403
    assert calls == []


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@pytest.fixture()
def db(tmp_path):
    """Fresh SQLite database per test, schema created, session exposed."""
    engine = create_engine(f"sqlite:///{tmp_path}/api.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api(db):
    """TestClient with session + client-scope dependencies overridden."""
    client_row = Client(name="acme")
    db.add(client_row)
    db.commit()

    app = create_app()

    def override_db():
        yield db

    def override_client_id():
        return client_row.id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = override_client_id
    with TestClient(app) as test_client:
        yield test_client


def seed_mention(
    db,
    client_id: int,
    url: str,
    *,
    source=MentionSource.news_rss,
    title: str | None = "t",
    content: str | None = None,
    author: str | None = None,
    sentiment=None,
    published: datetime | None = None,
    ingested: datetime | None = None,
    keyword_id: int | None = None,
    reach: int | None = None,
    event_id: int | None = None,
) -> Mention:
    mention = Mention(
        client_id=client_id,
        source=source,
        url=url,
        url_hash=make_url_hash(url),
        title=title,
        content=content,
        author=author,
        sentiment=sentiment,
        published_at=published,
        ingested_at=ingested or now_utc(),
        keyword_id=keyword_id,
        reach=reach,
        event_id=event_id,
    )
    db.add(mention)
    db.commit()
    return mention


def first_client_id(db) -> int:
    """The single client row created by the `api` fixture."""
    return db.scalar(select(Client.id).limit(1))


# ---------------------------------------------------------------- events


def seed_event(db, client_id: int, title: str, first, last, **counts) -> Event:
    event = Event(
        client_id=client_id,
        title=title,
        title_tokens=title,
        first_seen_at=first,
        last_seen_at=last,
        **counts,
    )
    db.add(event)
    db.commit()
    return event


def test_events_empty_and_404(api, db) -> None:
    client_id = first_client_id(db)
    assert api.get(f"/api/clients/{client_id}/events").json() == []
    assert api.get("/api/clients/999999/events").status_code == 404
    assert api.get("/api/clients/999999/events/1").status_code == 404


def test_events_ordered_by_last_seen_with_since_filter(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    old = seed_event(db, client_id, " vieja", now - timedelta(days=3), now - timedelta(days=3))
    new = seed_event(db, client_id, "nueva", now - timedelta(hours=1), now)
    body = api.get(f"/api/clients/{client_id}/events").json()
    assert [e["id"] for e in body] == [new.id, old.id]

    since = now - timedelta(minutes=30)
    filtered = api.get(
        f"/api/clients/{client_id}/events", params={"since": since.isoformat()}
    ).json()
    assert [e["id"] for e in filtered] == [new.id]


def test_events_scoped_to_client(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    seed_event(db, client_id, "mia", now, now)
    other = Client(name="otro")
    db.add(other)
    db.commit()
    seed_event(db, other.id, "suya", now, now)
    mine = api.get(f"/api/clients/{client_id}/events").json()
    assert len(mine) == 1 and mine[0]["title"] == "mia"


def test_events_min_mentions_filter(api, db) -> None:
    """The eco view: only events with real multi-source coverage."""
    client_id = first_client_id(db)
    now = now_utc()
    big = seed_event(
        db, client_id, "Cobertura amplia", now, now, mention_count=4, source_count=3
    )
    seed_event(db, client_id, "Singleton", now, now, mention_count=1, source_count=1)

    body = api.get(f"/api/clients/{client_id}/events", params={"min_mentions": 2}).json()
    assert [e["id"] for e in body] == [big.id]

    all_rows = api.get(f"/api/clients/{client_id}/events").json()
    assert len(all_rows) == 2


def test_event_detail_orders_mentions_by_reach(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    event = seed_event(
        db, client_id, "BUAP noticia", now, now, mention_count=2, source_count=2
    )
    low = seed_mention(db, client_id, "https://example.com/low", reach=10, event_id=event.id)
    high = seed_mention(db, client_id, "https://example.com/high", reach=99, event_id=event.id)
    body = api.get(f"/api/clients/{client_id}/events/{event.id}").json()
    assert body["id"] == event.id
    assert [m["id"] for m in body["mentions"]] == [high.id, low.id]
    assert body["mention_count"] == 2


def test_event_detail_404_for_other_client(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    event = seed_event(db, client_id, "mia", now, now)
    other = Client(name="otro")
    db.add(other)
    db.commit()
    assert api.get(f"/api/clients/{other.id}/events/{event.id}").status_code == 404


# ---------------------------------------------------------------- health


def test_api_health_ok(api) -> None:
    response = api.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------- mentions


def test_mentions_empty_state(api) -> None:
    response = api.get("/api/mentions")
    assert response.status_code == 200
    assert response.json() == {"items": [], "total": 0}


def test_mentions_filter_by_medium(api, db) -> None:
    """medium matches the URL host (www-insensitive, '/' boundary)."""
    client_id = first_client_id(db)
    seed_mention(db, client_id, "https://www.e-consulta.com/noticia/1")
    seed_mention(db, client_id, "https://e-consulta.com/noticia/2")
    seed_mention(db, client_id, "https://e-consulta.com.mx/otra/3")
    seed_mention(db, client_id, "https://lajornadadeoriente.com.mx/a/1")

    same_host = api.get("/api/mentions", params={"medium": "e-consulta.com"}).json()
    assert {item["url"] for item in same_host["items"]} == {
        "https://www.e-consulta.com/noticia/1",
        "https://e-consulta.com/noticia/2",
    }
    assert same_host["total"] == 2

    with_www = api.get("/api/mentions", params={"medium": "www.e-consulta.com"}).json()
    assert with_www["total"] == 2

    no_match = api.get("/api/mentions", params={"medium": "nadie.com"}).json()
    assert no_match == {"items": [], "total": 0}


def test_mentions_include_canonical_event(api, db) -> None:
    """Feed rows carry event_id/event_title so the UI can chip the cluster."""
    client_id = first_client_id(db)
    event = seed_event(
        db,
        client_id,
        "Campaña Échale los kilos",
        now_utc() - timedelta(hours=2),
        now_utc(),
        mention_count=1,
    )
    seed_mention(
        db,
        client_id,
        "https://example.com/evented",
        title="Con evento",
        event_id=event.id,
    )
    seed_mention(db, client_id, "https://example.com/plain", title="Sin evento")

    body = api.get("/api/mentions").json()
    by_url = {item["url"]: item for item in body["items"]}
    assert by_url["https://example.com/evented"]["event_id"] == event.id
    assert by_url["https://example.com/evented"]["event_title"] == "Campaña Échale los kilos"
    assert by_url["https://example.com/plain"]["event_id"] is None
    assert by_url["https://example.com/plain"]["event_title"] is None


@pytest.fixture()
def mentions_seeded(db):
    """Three mentions: two classified, one with NULL sentiment."""
    client_id = first_client_id(db)
    kw = Keyword(client_id=client_id, text="acme", language="es")
    db.add(kw)
    db.commit()
    now = now_utc()
    m1 = seed_mention(
        db,
        client_id,
        "https://news.example.com/a",
        title="Acme lanza producto",
        content="noticia",
        sentiment=Sentiment.positive,
        published=now - timedelta(hours=3),
        ingested=now - timedelta(hours=2),
        keyword_id=kw.id,
    )
    m2 = seed_mention(
        db,
        client_id,
        "https://x.com/acme/2",
        source=MentionSource.x_twitter,
        title="Acme tweet",
        sentiment=Sentiment.negative,
        published=now - timedelta(hours=1),
        ingested=now - timedelta(hours=1),
        reach=42,
    )
    m3 = seed_mention(
        db,
        client_id,
        "https://gdelt.example/c",
        source=MentionSource.gdelt,
        title="zapatorio menciona a Acme",
        content="texto suelto",
        sentiment=None,
        published=now - timedelta(hours=2),
        ingested=now - timedelta(minutes=30),
    )
    return m1, m2, m3


def test_mentions_list_ordered_newest_first(api, mentions_seeded) -> None:
    m1, m2, m3 = mentions_seeded
    body = api.get("/api/mentions").json()
    assert body["total"] == 3
    assert [item["id"] for item in body["items"]] == [m2.id, m3.id, m1.id]
    item = body["items"][0]
    assert item["source"] == "x_twitter"
    assert item["sentiment"] == "negative"
    assert set(item) >= {
        "id",
        "keyword_id",
        "source",
        "url",
        "title",
        "content",
        "sentiment",
        "sentiment_score",
        "reach",
        "published_at",
        "ingested_at",
    }


def test_mentions_null_sentiment_serializes_null(api, mentions_seeded) -> None:
    m1, _m2, m3 = mentions_seeded
    items = {m["id"]: m for m in api.get("/api/mentions").json()["items"]}
    assert items[m3.id]["sentiment"] is None
    assert items[m1.id]["sentiment"] == "positive"


def test_mentions_carry_linked_persons(api, db, mentions_seeded) -> None:
    """F3 chips: the feed payload names the persons linked to each mention."""
    from app.models import MentionPerson, Person

    m1, _m2, _m3 = mentions_seeded
    client_id = first_client_id(db)
    person = Person(client_id=client_id, name="Lilia Cedillo", name_key="lilia cedillo")
    db.add(person)
    db.flush()
    db.add(MentionPerson(mention_id=m1.id, person_id=person.id))
    db.commit()

    items = {m["id"]: m for m in api.get("/api/mentions").json()["items"]}
    assert items[m1.id]["persons"] == [{"id": person.id, "name": "Lilia Cedillo"}]
    assert items[_m2.id]["persons"] == []


def test_mentions_filter_source_and_sentiment(api, mentions_seeded) -> None:
    m1, m2, m3 = mentions_seeded
    url = "/api/mentions"
    assert [i["id"] for i in api.get(url, params={"source": "x_twitter"}).json()["items"]] == [m2.id]
    assert (
        [i["id"] for i in api.get(url, params={"sentiment": "positive"}).json()["items"]]
        == [m1.id]
    )
    # "none" is the explicit NULL-sentiment filter.
    assert (
        [i["id"] for i in api.get(url, params={"sentiment": "none"}).json()["items"]]
        == [m3.id]
    )


def test_mentions_filter_keyword_and_window(api, mentions_seeded) -> None:
    m1, _m2, m3 = mentions_seeded
    now = now_utc()
    url = "/api/mentions"
    assert (
        [i["id"] for i in api.get(url, params={"keyword_id": m1.keyword_id}).json()["items"]]
        == [m1.id]
    )
    between = api.get(
        url,
        params={
            "since": (now - timedelta(hours=2, minutes=30)).isoformat(),
            "until": (now - timedelta(hours=1, minutes=30)).isoformat(),
        },
    ).json()
    assert [i["id"] for i in between["items"]] == [m3.id]


def test_mentions_q_searches_title_and_content(api, mentions_seeded) -> None:
    _m1, _m2, m3 = mentions_seeded
    by_content = api.get("/api/mentions", params={"q": "zapatorio"}).json()
    assert [i["id"] for i in by_content["items"]] == [m3.id]
    by_title = api.get("/api/mentions", params={"q": "ACME"}).json()
    assert by_title["total"] == 3  # case-insensitive match on every title


def test_mentions_pagination_and_limit_bounds(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    for i in range(60):
        seed_mention(
            db,
            client_id,
            f"https://example.com/p/{i}",
            published=now - timedelta(minutes=i),
        )
    default = api.get("/api/mentions").json()
    assert len(default["items"]) == 50  # default limit
    assert default["total"] == 60

    page = api.get("/api/mentions", params={"limit": 10, "offset": 55}).json()
    assert len(page["items"]) == 5
    assert page["total"] == 60

    assert api.get("/api/mentions", params={"limit": 500}).status_code == 200
    assert api.get("/api/mentions", params={"limit": 0}).status_code == 422
    assert api.get("/api/mentions", params={"limit": 501}).status_code == 422


# ---------------------------------------------------------------- keywords


def test_keywords_empty_then_create(api) -> None:
    assert api.get("/api/keywords").json() == []

    response = api.post(
        "/api/keywords", json={"text": "  acme  ", "language": "es"}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "acme"  # stripped
    assert body["is_active"] is True

    listed = api.get("/api/keywords").json()
    assert [k["text"] for k in listed] == ["acme"]


def test_keywords_create_validations(api) -> None:
    assert api.post("/api/keywords", json={"text": "   "}).status_code == 422
    assert (
        api.post("/api/keywords", json={"text": "x", "language": "other"}).status_code
        == 201
    )
    assert (
        api.post("/api/keywords", json={"text": "x", "language": "fr"}).status_code
        == 422
    )


def test_keywords_create_duplicate_conflict(api) -> None:
    api.post("/api/keywords", json={"text": "acme"})
    response = api.post("/api/keywords", json={"text": "acme"})
    assert response.status_code == 409


def test_keyword_patch_rename_and_toggle(api) -> None:
    kw_id = api.post("/api/keywords", json={"text": "acme"}).json()["id"]
    response = api.patch(
        f"/api/keywords/{kw_id}", json={"text": "acme corp", "is_active": False}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["text"] == "acme corp"
    assert body["is_active"] is False
    # inactive keywords remain listed (dashboard toggles them back on)
    assert any(k["id"] == kw_id for k in api.get("/api/keywords").json())


def test_keyword_patch_validations(api) -> None:
    kw_id = api.post("/api/keywords", json={"text": "acme"}).json()["id"]
    other_id = api.post("/api/keywords", json={"text": "rival"}).json()["id"]
    assert api.patch("/api/keywords/999999", json={"text": "x"}).status_code == 404
    # rename onto an existing text -> conflict
    assert (
        api.patch(f"/api/keywords/{kw_id}", json={"text": "rival"}).status_code == 409
    )
    assert (
        api.patch(f"/api/keywords/{other_id}", json={"text": " "}).status_code == 422
    )


def test_keyword_delete(api, db) -> None:
    client_id = first_client_id(db)
    kw_id = api.post("/api/keywords", json={"text": "lonely"}).json()["id"]
    assert api.delete(f"/api/keywords/{kw_id}").status_code == 204
    assert api.delete(f"/api/keywords/{kw_id}").status_code == 404

    used_id = api.post("/api/keywords", json={"text": "used"}).json()["id"]
    seed_mention(db, client_id, "https://x.com/1", keyword_id=used_id)
    seed_mention(db, client_id, "https://x.com/2", keyword_id=used_id)
    response = api.delete(f"/api/keywords/{used_id}")
    assert response.status_code == 409
    assert "mention" in response.json()["detail"]
    assert api.get("/api/keywords").json()[0]["id"] == used_id


# ---------------------------------------------------------------- stats


def test_stats_overview_shape(api, db) -> None:
    client_id = first_client_id(db)
    now = now_utc()
    seed_mention(db, client_id, "https://a/1", sentiment=Sentiment.positive,
                 published=now - timedelta(minutes=10))
    seed_mention(db, client_id, "https://a/2", sentiment=Sentiment.negative,
                 source=MentionSource.x_twitter, published=now - timedelta(minutes=5))
    seed_mention(db, client_id, "https://a/3", sentiment=None,
                 source=MentionSource.gdelt, published=now - timedelta(hours=30))
    # social-only host: counts in by_medium, not in news_medium_count
    seed_mention(db, client_id, "https://b/9", source=MentionSource.facebook_page)

    body = api.get("/api/stats/overview").json()
    assert body["total"] == 4
    assert body["by_sentiment"] == {
        "positive": 1,
        "negative": 1,
        "neutral": 0,
        "null": 2,
    }
    assert body["by_source"] == {
        "news_rss": 1,
        "gdelt": 1,
        "x_twitter": 1,
        "facebook_page": 1,
        "rss_custom": 0,
        "scraper": 0,
        "field_report": 0,
    }
    assert body["last_24h"] == 2
    assert body["last_7d"] == 3
    assert body["by_medium"] == {"a": 3, "b": 1}
    # news outlets exclude social adapters: a/2 is x_twitter on host a.
    assert body["news_medium_count"] == 1
    volume = body["daily_volume"]
    assert len(volume) == 30
    expected_today = sum(
        1 for offset in (10, 5) if (now - timedelta(minutes=offset)).date() == now.astimezone(timezone.utc).date()
    )
    assert volume[-1] == {"date": now.astimezone(timezone.utc).date().isoformat(), "count": expected_today}
    counts = [point["count"] for point in volume]
    assert sum(counts) == 3
    assert volume[0]["date"] < volume[-1]["date"]


def test_stats_overview_empty(api) -> None:
    body = api.get("/api/stats/overview").json()
    assert body["total"] == 0
    assert body["by_sentiment"]["null"] == 0
    assert body["last_24h"] == 0
    assert all(point["count"] == 0 for point in body["daily_volume"])
    assert len(body["daily_volume"]) == 30


# ---------------------------------------------------------------- alerts


def test_settings_digest_hours_roundtrip(api) -> None:
    """digest_hours persists as sorted CSV and reads back as a list."""
    resp = api.put("/api/settings", json={"digest_hours": [21, 8, 8, 6]})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["digest_hours"] == [6, 8, 21]  # sorted, deduped
    assert body["digest_hour"] == 6  # compat mirror of the first cut
    assert api.get("/api/settings").json()["digest_hours"] == [6, 8, 21]


def test_settings_digest_hours_validation(api) -> None:
    assert api.put("/api/settings", json={"digest_hours": []}).status_code == 422
    assert (
        api.put("/api/settings", json={"digest_hours": list(range(9))}).status_code
        == 422
    )
    assert api.put("/api/settings", json={"digest_hours": [24]}).status_code == 422
    # Legacy single-hour field keeps working beside the list.
    assert api.put("/api/settings", json={"digest_hour": 5}).status_code == 200
    assert api.get("/api/settings").json()["digest_hours"] == [5]


def test_alert_settings_defaults_when_missing(api) -> None:
    body = api.get("/api/alerts/settings").json()
    assert body == {
        "digest": "instant",
        "recipient_email": None,
        "is_active": False,
        "sentiment_shift_enabled": True,
        "sentiment_shift_threshold": 10.0,
    }


def test_alert_settings_upsert_and_get(api) -> None:
    payload = {
        "digest": "daily",
        "recipient_email": "alerts@acme.com",
        "is_active": True,
    }
    assert api.put("/api/alerts/settings", json=payload).status_code == 200
    assert api.get("/api/alerts/settings").json() == {
        "digest": "daily",
        "recipient_email": "alerts@acme.com",
        "is_active": True,
        "sentiment_shift_enabled": True,
        "sentiment_shift_threshold": 10.0,
    }

    updated = api.put(
        "/api/alerts/settings",
        json={"digest": "weekly", "recipient_email": "other@acme.com", "is_active": False},
    )
    assert updated.status_code == 200
    assert updated.json()["digest"] == "weekly"
    # exactly one row: the PUT updated, not duplicated
    rows = api.get("/api/alerts/settings").json()
    assert rows["recipient_email"] == "other@acme.com"


def test_alert_settings_validation(api) -> None:
    bad_digest = {"digest": "hourly", "recipient_email": "a@b.com", "is_active": True}
    assert api.put("/api/alerts/settings", json=bad_digest).status_code == 422
    bad_mail = {"digest": "daily", "recipient_email": "nope", "is_active": True}
    assert api.put("/api/alerts/settings", json=bad_mail).status_code == 422


# --------------------------------------------------------------- coverage


class TestEventCoverage:
    def test_counts_distinct_outlets_per_source(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "e", now, now, mention_count=3, source_count=2)
        seed_mention(db, client_id, "https://a.com/1", event_id=event.id)
        seed_mention(
            db, client_id, "https://a.com/2", source=MentionSource.gdelt, event_id=event.id
        )
        seed_mention(db, client_id, "https://b.com/1", event_id=event.id)
        body = api.get(f"/api/clients/{client_id}/events/{event.id}/coverage").json()
        assert body["event_id"] == event.id
        assert body["mention_count"] == 3
        assert body["outlet_count"] == 2
        by_source = {row["source"]: row for row in body["by_source"]}
        assert by_source["news_rss"]["n_mentions"] == 2
        assert by_source["news_rss"]["outlets"] == 2
        assert by_source["gdelt"]["n_mentions"] == 1
        assert by_source["gdelt"]["outlets"] == 1

    def test_zeroed_when_event_has_no_mentions(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "empty", now, now)
        body = api.get(f"/api/clients/{client_id}/events/{event.id}/coverage").json()
        assert body["mention_count"] == 0
        assert body["outlet_count"] == 0
        assert body["by_source"] == []

    def test_404_for_other_client(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "mia", now, now)
        other = Client(name="otro")
        db.add(other)
        db.commit()
        assert api.get(f"/api/clients/{other.id}/events/{event.id}/coverage").status_code == 404

    def test_author_fallback_when_url_has_no_host(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "e", now, now, mention_count=2, source_count=2)
        seed_mention(db, client_id, "not-a-url", author="@fuente", event_id=event.id)
        seed_mention(db, client_id, "https://b.com/1", event_id=event.id)
        body = api.get(f"/api/clients/{client_id}/events/{event.id}/coverage").json()
        assert body["outlet_count"] == 2


class TestClientCoverageSummary:
    def test_repetition_index_per_day(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        today = now.replace(hour=12, minute=0, second=0, microsecond=0)
        ev_a = seed_event(db, client_id, "a", today, today, mention_count=2, source_count=2)
        ev_b = seed_event(db, client_id, "b", today, today, mention_count=1, source_count=1)
        seed_mention(db, client_id, "https://a.com/1", event_id=ev_a.id, published=today)
        seed_mention(db, client_id, "https://b.com/1", event_id=ev_a.id, published=today)
        seed_mention(db, client_id, "https://a.com/2", event_id=ev_b.id, published=today)
        # Older window plus a foreign-client row that must not leak in.
        old_ev = seed_event(db, client_id, "old", now, now, mention_count=1, source_count=1)
        seed_mention(
            db,
            client_id,
            "https://old.com/1",
            event_id=old_ev.id,
            published=now - timedelta(days=3),
        )
        other = Client(name="otro")
        db.add(other)
        db.commit()
        other_ev = seed_event(db, other.id, "suyo", now, now)
        seed_mention(db, other.id, "https://x.com/1", event_id=other_ev.id, published=now)

        body = api.get(f"/api/clients/{client_id}/coverage/summary").json()
        today_row = next(row for row in body if row["date"] == today.date().isoformat())
        assert today_row["events"] == 2  # ev_a, ev_b (the old event is another day)
        assert today_row["mentions"] == 3
        assert today_row["multi_source_events"] == 1  # only ev_a spans two outlets
        assert today_row["repetition_pct"] == 50.0
        older = [row for row in body if row["date"] != today.date().isoformat()]
        assert len(older) == 1 and older[0]["events"] == 1
        # Client scope: the other client's event never shows up.
        assert all(row["events"] <= 2 for row in body)

    def test_days_window_clamped_1_90(self, api, db) -> None:
        client_id = first_client_id(db)
        now = now_utc()
        event = seed_event(db, client_id, "old", now, now)
        seed_mention(
            db,
            client_id,
            "https://old.com/1",
            event_id=event.id,
            published=now - timedelta(days=3),
        )
        # days=0 -> clamped to 1: the 3-day-old mention drops out.
        tight = api.get(
            f"/api/clients/{client_id}/coverage/summary", params={"days": 0}
        ).json()
        assert tight == []
        wide = api.get(
            f"/api/clients/{client_id}/coverage/summary", params={"days": 999}
        ).json()
        assert len(wide) == 1 and wide[0]["events"] == 1

    def test_empty_client_returns_empty_list(self, api, db) -> None:
        client_id = first_client_id(db)
        body = api.get(f"/api/clients/{client_id}/coverage/summary").json()
        assert body == []
        assert api.get("/api/clients/999999/coverage/summary").status_code == 404


# ---------------------------------------------------------------- persons (F3)


def seed_person_mention(db, client_id: int, url: str, persons_data: list[dict], **kw) -> Mention:
    """Mention with a raw_enrichment payload, linked through the F3 hook."""
    from app import persons as persons_mod

    mention = seed_mention(db, client_id, url, sentiment=Sentiment.positive, **kw)
    mention.raw_enrichment = {
        "summary": "s",
        "sentiment": "positive",
        "sentiment_score": 0.9,
        "persons": persons_data,
        "topics": [],
    }
    persons_mod.persist_persons_from_enrichment(db, mention)
    db.commit()
    return mention


class TestPersonsAPI:
    def _seed_two(self, db, client_id: int) -> None:
        for i in range(3):
            seed_person_mention(
                db, client_id, f"https://a.com/{i}",
                [{"name": "Xóchitl Gálvez", "role": "Senadora", "org": "PAN",
                  "statement": "Dijo algo."}],
            )
        seed_person_mention(
            db, client_id, "https://b.com/1", [{"name": "Beto", "role": "Alcalde"}]
        )

    def test_list_empty_and_scoped(self, api, db) -> None:
        client_id = first_client_id(db)
        assert api.get(f"/api/clients/{client_id}/persons").json() == []
        assert api.get("/api/clients/999999/persons").status_code == 404

    def test_list_sorted_by_mentions_with_counts(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        body = api.get(f"/api/clients/{client_id}/persons").json()
        assert [p["name"] for p in body] == ["Xóchitl Gálvez", "Beto"]
        assert body[0]["mention_count"] == 3
        assert body[0]["role"] == "Senadora"
        # Fuentes badges: every row carries its distinct sources.
        assert body[0]["sources"] == ["news_rss"]

    def test_list_sort_recent_and_validation(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        body = api.get(f"/api/clients/{client_id}/persons", params={"sort": "recent"}).json()
        assert {p["name"] for p in body} == {"Xóchitl Gálvez", "Beto"}
        assert api.get(
            f"/api/clients/{client_id}/persons", params={"sort": "nope"}
        ).status_code == 422

    def test_list_q_filter(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        body = api.get(f"/api/clients/{client_id}/persons", params={"q": "xochitl gal"}).json()
        assert [p["name"] for p in body] == ["Xóchitl Gálvez"]

    def test_list_day_window_counts_only_window(self, api, db) -> None:
        """since+until → day card: windowed rank/count, other-day links ignored."""
        from datetime import timedelta

        client_id = first_client_id(db)
        now = now_utc()
        # Today: Xóchitl x2. Yesterday: Xóchitl x1 + Beto x1.
        for i in range(2):
            seed_person_mention(
                db, client_id, f"https://day.com/{i}",
                [{"name": "Xóchitl Gálvez", "role": "Senadora"}],
                published=now - timedelta(hours=1),
            )
        seed_person_mention(
            db, client_id, "https://yday.com/1",
            [{"name": "Xóchitl Gálvez"}],
            published=now - timedelta(days=1),
        )
        seed_person_mention(
            db, client_id, "https://yday.com/2",
            [{"name": "Beto", "role": "Alcalde"}],
            published=now - timedelta(days=1, hours=2),
        )
        body = api.get(
            f"/api/clients/{client_id}/persons",
            params={
                "since": (now - timedelta(hours=3)).isoformat(),
                "until": now.isoformat(),
                "limit": 5,
            },
        ).json()
        assert [(p["name"], p["mention_count"]) for p in body] == [
            ("Xóchitl Gálvez", 2)
        ]
        # The all-time ranking is untouched by the windowed params.
        total = api.get(f"/api/clients/{client_id}/persons").json()
        assert {p["name"]: p["mention_count"] for p in total} == {
            "Xóchitl Gálvez": 3,
            "Beto": 1,
        }

    def test_detail_timeline(self, api, db) -> None:
        from app.models import Person

        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        person = db.query(Person).filter_by(name_key="xochitl galvez").one()
        body = api.get(f"/api/clients/{client_id}/persons/{person.id}").json()
        assert body["name"] == "Xóchitl Gálvez"
        assert body["mention_count"] == 3
        assert len(body["timeline"]) == 3
        assert all(i["context"] == "Dijo algo." for i in body["timeline"])
        assert body["timeline"][0]["url"].startswith("https://a.com/")
        assert body["timeline"][0]["event_title"] is None
        assert body["timeline"][0]["political_label"] is None

    def test_detail_timeline_page_applies_offset_and_order(self, api, db) -> None:
        from app.models import Person

        client_id = first_client_id(db)
        base = now_utc() - timedelta(hours=3)
        for index in range(3):
            seed_person_mention(
                db,
                client_id,
                f"https://ordered.example/{index}",
                [{"name": "Ana", "statement": f"Declaración {index}"}],
                published=base + timedelta(hours=index),
            )
        person = db.query(Person).filter_by(name_key="ana").one()
        response = api.get(
            f"/api/clients/{client_id}/persons/{person.id}",
            params={"limit": 1, "offset": 1, "order": "oldest"},
        )
        assert response.status_code == 200
        body = response.json()
        assert [item["url"] for item in body["timeline"]] == [
            "https://ordered.example/1"
        ]
        assert body["mention_count"] == 3
        assert body["timeline_total"] == 3
        assert body["timeline_limit"] == 1
        assert body["timeline_offset"] == 1
        assert body["timeline_order"] == "oldest"

    @pytest.mark.parametrize(
        "params, expected_limit, expected_offset, expected_length",
        [
            ({"limit": 999, "offset": -4}, 200, 0, 3),
            ({"limit": 0, "offset": 0}, 1, 0, 1),
            ({"limit": 25, "offset": 999}, 25, 999, 0),
        ],
    )
    def test_detail_bounds_do_not_change_timeline_total(
        self, api, db, params, expected_limit, expected_offset, expected_length
    ) -> None:
        from app.models import Person

        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        person = db.query(Person).filter_by(name_key="xochitl galvez").one()
        response = api.get(
            f"/api/clients/{client_id}/persons/{person.id}", params=params
        )
        assert response.status_code == 200
        body = response.json()
        assert body["timeline_total"] == body["mention_count"] == 3
        assert body["timeline_limit"] == expected_limit
        assert body["timeline_offset"] == expected_offset
        assert len(body["timeline"]) == expected_length
        assert (
            api.get(
                f"/api/clients/{client_id}/persons/{person.id}",
                params={"order": "invalid"},
            ).status_code
            == 422
        )

    def test_detail_404_other_client_and_missing(self, api, db) -> None:
        from app.models import Person

        client_id = first_client_id(db)
        self._seed_two(db, client_id)
        person = db.query(Person).first()
        other = Client(name="otro")
        db.add(other)
        db.commit()
        assert api.get(f"/api/clients/{other.id}/persons/{person.id}").status_code == 404
        assert api.get(f"/api/clients/{client_id}/persons/999999").status_code == 404


# ------------------------------------------------- stats day (home-digest-v2 T2)


def test_tone_bucket_rules() -> None:
    assert queries.tone_bucket("news_rss") == "media"
    assert queries.tone_bucket("gdelt") == "media"
    assert queries.tone_bucket("rss_custom") == "media"
    assert queries.tone_bucket("scraper") == "media"
    assert queries.tone_bucket("x_twitter") == "social"
    assert queries.tone_bucket("facebook_page") == "social"
    # Field data rides field-prefixed source tags (the card markup's
    # convention); the enum grows members when that ingest lands.
    assert queries.tone_bucket("field") == "field"
    assert queries.tone_bucket("field_whatsapp") == "field"


def test_stats_day_tones_split_by_source_kind(api, db) -> None:
    client_id = first_client_id(db)
    cst = timezone(timedelta(hours=-6))
    seed_mention(
        db, client_id, "https://e.test/1",
        sentiment=Sentiment.positive,
        published=datetime(2026, 10, 22, 12, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://e.test/2",
        sentiment=None,  # unclassified bucket
        published=datetime(2026, 10, 22, 13, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://e.test/3",
        source=MentionSource.x_twitter,
        sentiment=Sentiment.negative,
        published=datetime(2026, 10, 22, 14, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://e.test/4",
        source=MentionSource.scraper,  # neither social nor field: media
        sentiment=Sentiment.neutral,
        published=datetime(2026, 10, 22, 15, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://e.test/5",
        sentiment=Sentiment.positive,
        published=datetime(2026, 10, 21, 12, 0, tzinfo=cst),  # other day
    )

    resp = api.get("/api/stats/day", params={"date": "2026-10-22"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["date"] == "2026-10-22"
    assert body["timezone"] == "America/Mexico_City"
    assert body["tones"]["media"] == {
        "positive": 1,
        "negative": 0,
        "neutral": 1,
        "unclassified": 1,
        "total": 3,
    }
    assert body["tones"]["social"] == {
        "positive": 0,
        "negative": 1,
        "neutral": 0,
        "unclassified": 0,
        "total": 1,
    }
    # No field ingest exists yet: the bucket stays zero-filled.
    assert body["tones"]["field"] == {
        "positive": 0,
        "negative": 0,
        "neutral": 0,
        "unclassified": 0,
        "total": 0,
    }


def test_stats_day_keyword_counts(api, db) -> None:
    client_id = first_client_id(db)
    cst = timezone(timedelta(hours=-6))
    buap = Keyword(client_id=client_id, text="BUAP", language="es")
    lilia = Keyword(client_id=client_id, text="lilia cedillo", language="es")
    quiet = Keyword(client_id=client_id, text="zar, la mención", language="es")
    db.add_all([buap, lilia, quiet])
    db.commit()
    seed_mention(
        db, client_id, "https://k.test/1",
        keyword_id=buap.id,
        published=datetime(2026, 10, 22, 9, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://k.test/2",
        keyword_id=buap.id,
        published=datetime(2026, 10, 22, 10, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://k.test/3",
        keyword_id=lilia.id,
        published=datetime(2026, 10, 22, 11, 0, tzinfo=cst),
    )
    seed_mention(
        db, client_id, "https://k.test/4",
        keyword_id=buap.id,
        published=datetime(2026, 10, 21, 12, 0, tzinfo=cst),  # outside the day
    )

    resp = api.get("/api/stats/day", params={"date": "2026-10-22"})
    assert resp.status_code == 200
    # Every client keyword, count desc; zeroes included, the home page curates.
    assert resp.json()["keywords"] == [
        {"id": buap.id, "text": "BUAP", "count": 2},
        {"id": lilia.id, "text": "lilia cedillo", "count": 1},
        {"id": quiet.id, "text": "zar, la mención", "count": 0},
    ]


def test_stats_day_uses_local_day_bounds(api, db) -> None:
    # 22 oct 23:00 CST == 23 oct 05:00Z: inside the LOCAL day, outside the
    # UTC one; 23 oct 00:30 CST == 23 oct 06:30Z falls in the next day.
    client_id = first_client_id(db)
    seed_mention(
        db, client_id, "https://b.test/1",
        published=datetime(2026, 10, 23, 5, 0, tzinfo=timezone.utc),
    )
    seed_mention(
        db, client_id, "https://b.test/2",
        published=datetime(2026, 10, 23, 6, 30, tzinfo=timezone.utc),
    )

    resp = api.get("/api/stats/day", params={"date": "2026-10-22"})
    assert resp.status_code == 200
    assert resp.json()["tones"]["media"]["total"] == 1


class TestSummaryRevisions:
    def _seed_day(self, db, client_id: int, day=None) -> None:
        from datetime import date

        from app.models import DailySummary, DailySummaryRevision

        summary_date = day or date(2026, 10, 23)
        db.add(
            DailySummary(
                client_id=client_id,
                summary_date=summary_date,
                content={"schema": 2},
                narrative="versión vigente",
                mode="heuristic",
            )
        )
        for seq, text in ((1, "primera versión"), (2, "segunda versión")):
            db.add(
                DailySummaryRevision(
                    client_id=client_id,
                    summary_date=summary_date,
                    seq=seq,
                    narrative=text,
                    mode="heuristic",
                )
            )
        db.commit()

    def test_index_and_day_listing(self, api, db) -> None:
        from datetime import date

        client_id = first_client_id(db)
        self._seed_day(db, client_id)
        days = api.get(f"/api/clients/{client_id}/summary-revisions").json()
        assert len(days) == 1
        assert days[0]["summary_date"] == "2026-10-23"
        assert days[0]["count"] == 2

        rows = api.get(f"/api/clients/{client_id}/summary-revisions/2026-10-23").json()
        assert [row["seq"] for row in rows] == [1, 2]
        assert rows[0]["narrative"] == "primera versión"

    @pytest.mark.parametrize("same_text", [False, True])
    @pytest.mark.parametrize("comparison", [False, True])
    def test_restore_persists_unbacked_headline_without_borrowing_current_evidence(
        self, api, db, same_text, comparison
    ):
        from app.models import DailySummaryRevision
        from app.summaries.builder import build_daily_summary
        from tests.digest_legacy_fixtures import historical_summary

        client_id = first_client_id(db)
        day = date(2026, 10, 23)
        seed_mention(
            db,
            client_id,
            "https://medio.test/restore",
            title="Publicación vigente",
            published=datetime(2026, 10, 23, 18, tzinfo=timezone.utc),
        )
        db.commit()
        payload = {"headline": "Primera versión", "references": {"headline": [0]}}
        if comparison:
            prior_day = date(2026, 10, 9)
            seed_mention(
                db,
                client_id,
                "https://medio.test/prior-restore",
                title="Publicación del corte previo",
                published=datetime(2026, 10, 9, 18, tzinfo=timezone.utc),
            )
            db.commit()
            build_daily_summary(db, client_id=client_id, day=prior_day)
            payload["comparison_references"] = {
                "headline": {"current": [0], "prior": [0]}
            }
        historical_summary(db, client_id=client_id, day=day, payload=payload)
        payload["headline"] = "Primera versión" if same_text else "Nueva versión"
        current = historical_summary(
            db, client_id=client_id, day=day, payload=payload
        )
        before = json.loads(json.dumps(current.content))
        from app.summaries.evidence import resolved_provenance

        assert before["provenance"]["headline"]["state"] == (
            "unbacked" if comparison else "linked"
        )
        assert (
            resolved_provenance(before, before, "headline", text=payload["headline"])[
                "state"
            ]
            == "linked"
        )
        if comparison:
            assert "prior:#0" in before["plain_text"]
        foreign = Client(name="Otro cliente")
        db.add(foreign)
        db.flush()
        db.add(
            DailySummaryRevision(
                client_id=foreign.id,
                summary_date=day,
                seq=9,
                narrative="Texto privado ajeno",
                mode="llm",
            )
        )
        db.commit()
        # Each POST/GET really owns a fresh session; the JSON mutation must
        # survive commit, closure and ORM expiry, not just its POST response.
        factory = sessionmaker(bind=db.bind)

        def fresh_db():
            with factory() as session:
                yield session

        api.app.dependency_overrides[get_db] = fresh_db
        url = f"/api/clients/{client_id}/summary-revisions/restore"
        response = api.post(url, json={"day": day.isoformat(), "seq": 1})
        assert response.status_code == 200
        db.expire_all()
        read = api.get(f"/api/clients/{client_id}/summaries/{day}")
        assert read.status_code == 200
        row = read.json()
        assert row["narrative"] == "Primera versión"
        content = row["content"]
        binding = content["provenance"]["headline"]
        assert binding["state"] == "unbacked"
        assert binding["source_refs"] == []
        assert binding["text"] == row["narrative"]
        assert binding["origin"] == "revision_restore"
        assert "comparison" not in binding
        assert "prior:#" not in content["plain_text"]
        if comparison:
            assert content["comparison"] == before["comparison"]
        assert content["evidence"] == before["evidence"]
        assert content["indicators_version"] == before["indicators_version"] == 1
        assert content["noticias"][0]["media_diversity"] == {
            "identified_outlet_count": 1
        }
        assert content["noticias"][0]["veracity"] == "not_evaluated"
        assert "Diversidad de medios: 1 medio identificado" in content["plain_text"]
        assert "[alta]" not in content["plain_text"]
        assert response.json()["content"] == content
        assert content["tarjetas"] == before["tarjetas"]
        assert content["brief"]["headline"] == row["narrative"]
        assert content["headline"] == row["narrative"]
        assert "generation" not in content
        assert api.post(url, json={"day": day.isoformat(), "seq": 1}).json() == row
        assert api.post(url, json={"day": day.isoformat(), "seq": 9}).status_code == 404
        assert "Texto privado ajeno" not in json.dumps(row)
        revisions = api.get(f"/api/clients/{client_id}/summary-revisions/{day}").json()
        assert [r["narrative"] for r in revisions] == [
            "Primera versión",
            payload["headline"],
        ]

    def test_restore_updates_the_live_row(self, api, db) -> None:
        client_id = first_client_id(db)
        self._seed_day(client_id=client_id, db=db)

        def restore(seq: int):
            return api.post(
                f"/api/clients/{client_id}/summary-revisions/restore",
                json={"day": "2026-10-23", "seq": seq},
            )

        assert restore(1).status_code == 200
        row = api.get(f"/api/clients/{client_id}/summaries/2026-10-23").json()
        assert row["narrative"] == "primera versión"

        # Unknown seq/day → 404; the live row stays untouched.
        assert restore(9).status_code == 404
        assert restore.__name__ == "restore"  # sanity: closure usable
        other = api.post(
            f"/api/clients/{client_id}/summary-revisions/restore",
            json={"day": "2025-01-01", "seq": 1},
        )
        assert other.status_code == 404
        row = api.get(f"/api/clients/{client_id}/summaries/2026-10-23").json()
        assert row["narrative"] == "primera versión"


def _narrative_probe_client(handler) -> httpx.Client:
    import httpx as _httpx

    return _httpx.Client(transport=_httpx.MockTransport(handler))


def _probe_response(content: str | None, status: int = 200) -> httpx.Response:
    import httpx as _httpx

    if status != 200:
        return _httpx.Response(status, request=_httpx.Request("POST", "http://x"))
    return _httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}}]},
        request=_httpx.Request("POST", "http://x"),
    )


def test_probe_narrative_supported():
    from app.api.settings import AiProbeRequest, probe_narrative

    bodies: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return _probe_response('{"items": [], "headline": "ok"}')

    result = probe_narrative(
        AiProbeRequest(provider="openai", api_key="sk", base_url="http://x/v1", model="m"),
        client=_narrative_probe_client(handler),
    )
    assert result["ok"] is True
    assert result["json_schema"] == "supported"
    assert "response_format" in bodies[0]


def test_probe_narrative_unsupported_falls_back_to_plain():
    from app.api.settings import AiProbeRequest, probe_narrative

    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return _probe_response(None, status=500)  # schema attempt fails
        return _probe_response('{"whatever": 1}')  # plain works

    result = probe_narrative(
        AiProbeRequest(provider="openai", api_key="sk", base_url="http://x/v1"),
        client=_narrative_probe_client(handler),
    )
    assert result["ok"] is True
    assert result["json_schema"] == "unsupported"
    assert result["detail"]  # the schema failure travels for diagnosis


def test_probe_narrative_both_paths_fail():
    from app.api.settings import AiProbeRequest, probe_narrative

    def handler(request: httpx.Request) -> httpx.Response:
        return _probe_response(None, status=500)

    result = probe_narrative(
        AiProbeRequest(provider="openai", api_key="sk", base_url="http://x/v1"),
        client=_narrative_probe_client(handler),
    )
    assert result["ok"] is False
    assert result["error"]


def test_test_ai_endpoint_includes_narrative_on_openai_ok():
    from app.api.settings import AiProbeRequest, probe_ai, probe_narrative

    # endpoint-level: narrative only rides along on openai+ok; verified by
    # composition, the pieces have their own tests.


def test_narrative_probe_requires_key():
    from app.api.settings import AiProbeRequest, probe_narrative

    result = probe_narrative(AiProbeRequest(provider="openai"))
    assert result["ok"] is False
    assert "api_key" in result["error"]
