"""Saved-search API tests: CRUD, validation, client scoping (T1)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import create_app
from app.models import Base, Client, SavedSearch


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/saved.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    # Two tenants: scoping assertions need both.
    session.add(Client(name="acme"))
    session.add(Client(name="globex"))
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api(db):
    app = create_app()

    def override_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client


def _create(api, client_id: int = 1, **overrides) -> dict:
    payload = {"name": "Brand X", "query": "\"Brand X\"", **overrides}
    response = api.post(f"/api/clients/{client_id}/saved-searches", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_returns_defaults_and_location(api) -> None:
    row = _create(api, sources=["news_rss", "gdelt"], classifier="political")
    assert row["id"] > 0
    assert row["client_id"] == 1
    assert row["query"] == '"Brand X"'
    assert row["sources"] == ["news_rss", "gdelt"]
    assert row["classifier"] == "political"
    assert row["label"] is None
    assert row["range_days"] == 7
    assert row["is_active"] is True


def test_create_validates_payload(api) -> None:
    missing_query = api.post("/api/clients/1/saved-searches", json={"name": "x"})
    assert missing_query.status_code == 422
    empty_query = api.post(
        "/api/clients/1/saved-searches", json={"name": "x", "query": "  "}
    )
    assert empty_query.status_code == 422


def test_create_rejects_unknown_source(api) -> None:
    response = api.post(
        "/api/clients/1/saved-searches",
        json={"name": "bad src", "query": "q", "sources": ["instagram"]},
    )
    assert response.status_code == 422
    assert "sources" in response.json()["detail"]


def test_list_scoped_to_client(api, db) -> None:
    _create(api, client_id=1)
    _create(api, client_id=2, name="Globex watch", query="globex")
    first = api.get("/api/clients/1/saved-searches").json()
    second = api.get("/api/clients/2/saved-searches").json()
    assert [row["name"] for row in first] == ["Brand X"]
    assert [row["name"] for row in second] == ["Globex watch"]


def test_get_requires_client_scope(api) -> None:
    row = _create(api, client_id=1)
    other = api.get(f"/api/clients/2/saved-searches/{row['id']}")
    assert other.status_code == 404
    assert api.get(f"/api/clients/1/saved-searches/{row['id']}").status_code == 200


def test_update_partial_and_validation(api) -> None:
    row = _create(api)
    updated = api.patch(
        f"/api/clients/1/saved-searches/{row['id']}", json={"is_active": False}
    )
    assert updated.status_code == 200
    body = updated.json()
    assert body["is_active"] is False
    assert body["query"] == '"Brand X"'  # untouched

    bad = api.patch(
        f"/api/clients/1/saved-searches/{row['id']}", json={"range_days": 0}
    )
    assert bad.status_code == 422


def test_update_cross_client_404(api) -> None:
    row = _create(api, client_id=1)
    response = api.patch(
        f"/api/clients/2/saved-searches/{row['id']}", json={"is_active": False}
    )
    assert response.status_code == 404


def test_delete_and_unknown_client(api) -> None:
    row = _create(api)
    assert api.delete(f"/api/clients/1/saved-searches/{row['id']}").status_code == 204
    assert api.delete(f"/api/clients/1/saved-searches/{row['id']}").status_code == 404
    assert api.delete("/api/clients/999/saved-searches/1").status_code == 404


def test_duplicate_name_same_client_409_other_client_ok(api) -> None:
    _create(api, client_id=1)
    conflict = api.post(
        "/api/clients/1/saved-searches", json={"name": "Brand X", "query": "q"}
    )
    assert conflict.status_code == 409
    assert (
        api.post(
            "/api/clients/2/saved-searches", json={"name": "Brand X", "query": "q"}
        ).status_code
        == 201
    )


def test_unknown_client_404_on_create_and_list(api, db) -> None:
    assert api.post(
        "/api/clients/999/saved-searches", json={"name": "x", "query": "y"}
    ).status_code == 404
    assert api.get("/api/clients/999/saved-searches").status_code == 404
    assert db.scalar(select(func.count()).select_from(SavedSearch)) == 0


def test_source_readiness_defaults_unconfigured(api) -> None:
    """Free mode / no FB pages / no feeds => only news_rss ready."""
    resp = api.get("/api/clients/1/source-readiness")
    assert resp.status_code == 200
    body = resp.json()
    assert body["news_rss"] is True
    assert body["x_twitter"] is False
    assert body["facebook_page"] is False
    assert body["rss_custom"] is False


def test_source_readiness_x_from_settings_and_unknown_client(api) -> None:
    """x_twitter is ready only in paid mode with a stored key."""
    assert api.put(
        "/api/settings", json={"x_mode": "paid", "x_api_key": "k"}
    ).status_code == 200
    body = api.get("/api/clients/1/source-readiness").json()
    assert body["x_twitter"] is True
    assert api.get("/api/clients/999/source-readiness").status_code == 404
