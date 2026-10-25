"""x-mode settings: free/paid switch, key masking, worker wiring.

Covers the full settings chain for the X source mode:
model defaults -> upsert validation (mode enum, keep-on-empty key) ->
runtime resolution -> worker adapter selection (free index vs paid
provider, paid-without-key fallback) -> API masking (the stored key is
never serialized; only x_api_key_set leaks its existence).
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import worker
from app.api.deps import get_client_id
from app.db import get_db
from app.main import create_app
from app.models import Base, Client, queries
from app.models.settings import ClientSettings
from app.settings_runtime import EffectiveSettings, resolve_effective_settings


@pytest.fixture()
def session(tmp_path):
    # File-backed (not :memory:): the TestClient runs endpoints in another
    # thread, and in-memory SQLite connections are thread-local.
    engine = create_engine(f"sqlite:///{tmp_path}/x_mode.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def client_id(session) -> int:
    row = Client(name="acme")
    session.add(row)
    session.commit()
    return row.id


@pytest.fixture()
def api(session, client_id):
    app = create_app()

    def override_db():
        yield session

    def override_client_id():
        return client_id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = override_client_id
    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------- model/chain


def test_defaults_free_mode_without_key(session, client_id) -> None:
    row = queries.get_settings(session, client_id)
    assert row.x_mode == "free"
    assert row.x_api_key is None
    assert row.x_api_key_set is False


def test_upsert_x_mode_paid_reaches_runtime(session, client_id) -> None:
    queries.upsert_settings(session, client_id, {"x_mode": "paid", "x_api_key": " sk "})
    row = session.get(ClientSettings, queries.get_settings(session, client_id).id)
    assert row.x_mode == "paid"
    assert row.x_api_key == "sk"  # stored stripped
    effective = resolve_effective_settings(session, client_id=client_id)
    assert effective.x_mode == "paid"
    assert effective.x_api_key == "sk"


def test_upsert_x_mode_rejects_unknown_values(session, client_id) -> None:
    for bad in ("off", "FREE", "", None, 1):
        with pytest.raises(ValueError):
            queries.upsert_settings(session, client_id, {"x_mode": bad})


def test_upsert_x_api_key_empty_keeps_stored_key(session, client_id) -> None:
    """Empty (and null) PUT values conserve the stored key (masking UI)."""
    queries.upsert_settings(session, client_id, {"x_api_key": "secret"})
    for keep in ("", "   ", None):
        row = queries.upsert_settings(session, client_id, {"x_api_key": keep})
        assert row.x_api_key == "secret"


# ------------------------------------------------------------- worker wire


def _effective(**overrides) -> EffectiveSettings:
    return EffectiveSettings(client_id=1, **overrides)


def test_free_mode_builds_index_adapter() -> None:
    adapters = worker.build_adapters(_effective())
    assert [a.name for a in adapters] == ["google_news", "x_index", "gdelt"]


def test_paid_mode_with_key_builds_provider_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(worker.settings, "x_provider_base_url", "https://api.twitterapi.io")
    monkeypatch.setattr(worker.settings, "x_provider_rate_per_min", 5.0)
    adapters = worker.build_adapters(_effective(x_mode="paid", x_api_key="sk"))
    # Exclusive modes: the paid provider replaces the free index adapter.
    assert [a.name for a in adapters] == ["google_news", "x_twitter", "gdelt"]
    assert adapters[1]._api_key == "sk"  # key came from settings, not env
    assert adapters[1].search_url == "https://api.twitterapi.io/twitter/tweet/advanced_search"


def test_paid_mode_without_key_falls_back_with_warning(caplog) -> None:
    with caplog.at_level(logging.WARNING, logger="worker"):
        adapters = worker.build_adapters(_effective(x_mode="paid", x_api_key=None))
    assert [a.name for a in adapters] == ["google_news", "x_index", "gdelt"]
    assert any("x_api_key" in record.message for record in caplog.records)


# ------------------------------------------------------------------- API


def test_api_put_and_get_masks_the_key(api, session, client_id) -> None:
    resp = api.put(
        "/api/settings", json={"x_mode": "paid", "x_api_key": "supersecret"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["x_mode"] == "paid"
    assert body["x_api_key"] == ""
    assert body["x_api_key_set"] is True

    got = api.get("/api/settings").json()
    assert got["x_mode"] == "paid"
    assert got["x_api_key"] == ""
    assert got["x_api_key_set"] is True
    # The stored row keeps the real key; only the API masks it.
    assert queries.get_settings(session, client_id).x_api_key == "supersecret"


def test_api_put_empty_key_keeps_previous(api) -> None:
    api.put("/api/settings", json={"x_mode": "paid", "x_api_key": "one"})
    api.put("/api/settings", json={"x_api_key": ""})
    body = api.get("/api/settings").json()
    assert body["x_mode"] == "paid"  # untouched by the key-only update
    assert body["x_api_key_set"] is True


def test_api_defaults_and_validation(api) -> None:
    body = api.get("/api/settings").json()
    assert body["x_mode"] == "free"
    assert body["x_api_key"] == ""
    assert body["x_api_key_set"] is False
    assert api.put("/api/settings", json={"x_mode": "off"}).status_code == 422


def test_source_readiness_follows_settings(api, session, client_id) -> None:
    """Saved-search gating mirrors build_adapters: paid+key -> ready."""
    assert api.get(f"/api/clients/{client_id}/source-readiness").json()["x_twitter"] is False
    api.put("/api/settings", json={"x_mode": "paid", "x_api_key": "sk"})
    assert api.get(f"/api/clients/{client_id}/source-readiness").json()["x_twitter"] is True
    # Paid without a stored key is NOT ready (worker falls back to the
    # index); empty PUTs keep the key, so flip the row directly.
    row = queries.get_settings(session, client_id)
    row.x_api_key = None
    session.commit()
    assert api.get(f"/api/clients/{client_id}/source-readiness").json()["x_twitter"] is False


def test_ai_model_fast_roundtrip_and_runtime_fallback(api, session, client_id) -> None:
    """T2a: the fast/structured model override persists, clears, and the
    runtime falls back to the main model when unset."""
    from app.settings_runtime import resolve_effective_settings

    api.put("/api/settings", json={"ai_model": "big-model", "ai_model_fast": "flash"})
    body = api.get("/api/settings").json()
    assert body["ai_model_fast"] == "flash"
    assert body["ai_model"] == "big-model"
    effective = resolve_effective_settings(session, client_id)
    assert effective.fast_model == "flash"

    # Clearing the override falls back to the main model.
    api.put("/api/settings", json={"ai_model_fast": None})
    effective = resolve_effective_settings(session, client_id)
    assert effective.fast_model == "big-model"
    assert effective.ai_model == "big-model"
