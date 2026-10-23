"""API tests for the agenda feature: /api/clients/{id}/agenda-items CRUD.

Contract (odd/tasks/agenda-page.md): title-only creation, kind in
{activity, deadline}, undated items (event_date NULL) sort into «Sin fecha
completa», PATCH promotes/edits the date, everything client-scoped.

Fixture shape mirrors test_api: per-test SQLite + dependency overrides.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import get_client_id
from app.db import get_db
from app.main import create_app
from app.models import Base, Client


@pytest.fixture()
def db(tmp_path):
    """Fresh SQLite database per test, schema created, session exposed."""
    engine = create_engine(f"sqlite:///{tmp_path}/agenda.db")
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


def _main_client_id(db) -> int:
    row = db.query(Client).order_by(Client.id).first()
    assert row is not None
    return row.id


def _create(api: TestClient, client_id: int, **overrides) -> dict:
    payload = {"title": "Taller de cáncer de mama", **overrides}
    response = api.post(f"/api/clients/{client_id}/agenda-items", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_minimal_activity(api, db) -> None:
    item = _create(api, _main_client_id(db))
    assert item["title"] == "Taller de cáncer de mama"
    assert item["kind"] == "activity"
    assert item["event_date"] is None
    assert item["id"] > 0


def test_create_blank_title_422(api, db) -> None:
    response = api.post(
        f"/api/clients/{_main_client_id(db)}/agenda-items", json={"title": "  "}
    )
    assert response.status_code == 422


def test_create_rejects_unknown_kind(api, db) -> None:
    response = api.post(
        f"/api/clients/{_main_client_id(db)}/agenda-items",
        json={"title": "X", "kind": "nota"},
    )
    assert response.status_code == 422


def test_create_unknown_client_404(api) -> None:
    response = api.post("/api/clients/999999/agenda-items", json={"title": "X"})
    assert response.status_code == 404


def test_list_orders_dated_first_and_scopes_by_client(api, db) -> None:
    client_id = _main_client_id(db)
    other = Client(name="other")
    db.add(other)
    db.commit()

    _create(api, client_id, title="Sin fecha", date_label="27 oct.")
    _create(api, client_id, title="Zoned", event_date="2026-11-02", kind="deadline")
    _create(api, client_id, title="Earlier", event_date="2026-10-25")
    _create(api, other.id, title="Ajeno")

    items = api.get(f"/api/clients/{client_id}/agenda-items").json()
    titles = [item["title"] for item in items]
    assert "Ajeno" not in titles
    # Dated ascending first, undated last.
    assert titles == ["Earlier", "Zoned", "Sin fecha"]
    assert items[0]["event_date"] == "2026-10-25"
    assert items[2]["event_date"] is None
    assert items[2]["date_label"] == "27 oct."


def test_patch_promotes_date_and_keeps_rest(api, db) -> None:
    client_id = _main_client_id(db)
    item = _create(
        api,
        client_id,
        title="Bestias Eternas",
        kind="deadline",
        date_label="15 nov.",
        time_label="18:00",
        source="Resumen del día",
    )

    patched = api.patch(
        f"/api/clients/{client_id}/agenda-items/{item['id']}",
        json={"event_date": "2026-11-15"},
    )
    assert patched.status_code == 200
    body = patched.json()
    assert body["event_date"] == "2026-11-15"
    # Everything else preserved.
    assert body["kind"] == "deadline"
    assert body["time_label"] == "18:00"
    assert body["date_label"] == "15 nov."


def test_patch_validates_kind_and_date(api, db) -> None:
    client_id = _main_client_id(db)
    item = _create(api, client_id)
    url = f"/api/clients/{client_id}/agenda-items/{item['id']}"

    assert api.patch(url, json={"kind": "x"}).status_code == 422
    assert api.patch(url, json={"event_date": "noviembre"}).status_code == 422


def test_patch_cross_client_404(api, db) -> None:
    client_id = _main_client_id(db)
    other = Client(name="other")
    db.add(other)
    db.commit()
    item = _create(api, client_id)

    response = api.patch(
        f"/api/clients/{other.id}/agenda-items/{item['id']}", json={"title": "X"}
    )
    assert response.status_code == 404
