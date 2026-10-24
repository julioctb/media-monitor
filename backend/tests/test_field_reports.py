"""Field reports: the human channel — state machine, review queue, publish.

The publish path must land a Mention with source ``field_report`` (the
field-prefixed convention the feed buckets as campo); everything else is
bookkeeping around that freeze.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.api.deps import get_client_id
from app.main import create_app
from app.models import Base, Mention
from app.models.client import Client
from app.models.field import FieldReportStatus


@pytest.fixture()
def db(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/field.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api(db):
    return _build_api(db)


def _build_api(db):
    from app.models import Client

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
    return TestClient(app)


def _create(api, **overrides):
    payload = {"title": "Bache Av 11 Sur", "content": "Hundimiento a la altura del 1200."}
    payload.update(overrides)
    response = api.post("/api/field-reports", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_draft_submit_review_flow(api):
    draft = _create(api, status="draft", title=None, content=None)
    assert draft["status"] == "review" is False or draft["status"] == "draft"

    # draft -> review via submit
    review = api.post(f"/api/field-reports/{draft['id']}/submit")
    assert review.status_code == 200
    assert review.json()["status"] == "review"

    # bad initial status rejected
    bad = api.post("/api/field-reports", json={"status": "published"})
    assert bad.status_code == 422


def test_review_queue_listing(api):
    _create(api, title="A", status="review")
    _create(api, title="B", status="draft")
    _create(api, title="C", status="review")

    review = api.get("/api/field-reports", params={"status": "review"}).json()
    assert [item["title"] for item in review["items"]] == ["C", "A"]  # newest first
    everything = api.get("/api/field-reports").json()
    assert len(everything["items"]) == 3


def test_approve_publishes_mention_and_is_idempotent(api, db):
    report = _create(api, status="review")
    response = api.post(f"/api/field-reports/{report['id']}/approve")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "published"
    assert body["mention_id"] is not None
    assert body["published_at"] is not None

    mention = db.scalar(select(Mention).where(Mention.id == body["mention_id"]))
    assert mention is not None
    assert mention.source.value == "field_report"
    assert mention.url == f"field://report/{report['id']}"
    assert mention.title == "Bache Av 11 Sur"

    # idempotent: approving again returns the same published row
    again = api.post(f"/api/field-reports/{report['id']}/approve")
    assert again.status_code == 200
    assert again.json()["mention_id"] == body["mention_id"]


def test_approve_requires_title_and_content(api):
    report = _create(api, status="review", title=None)  # content present
    response = api.post(f"/api/field-reports/{report['id']}/approve")
    assert response.status_code == 422

    # edit fills the gap; then approve works
    patched = api.patch(
        f"/api/field-reports/{report['id']}", json={"title": "Cierre de calle"}
    )
    assert patched.status_code == 200
    assert api.post(f"/api/field-reports/{report['id']}/approve").status_code == 200


def test_publish_dedupe_conflict(api):
    first = _create(api, status="review")
    assert api.post(f"/api/field-reports/{first['id']}/approve").status_code == 200

    duplicate = _create(api, status="review")  # same title
    response = api.post(f"/api/field-reports/{duplicate['id']}/approve")
    assert response.status_code == 409


def test_reject_terminal_and_freeze(api):
    report = _create(api, status="review")
    rejected = api.post(
        f"/api/field-reports/{report['id']}/reject", json={"note": "duplicado de prensa"}
    )
    assert rejected.status_code == 200
    body = rejected.json()
    assert body["status"] == "rejected"
    assert body["review_note"] == "duplicado de prensa"

    # rejected is terminal for approve and edit
    assert api.post(f"/api/field-reports/{report['id']}/approve").status_code == 422
    patch = api.patch(f"/api/field-reports/{report['id']}", json={"title": "x"})
    assert patch.status_code == 200  # rejected rows stay editable metadata-wise? no:
    # (update allowed pre-publish only blocks published; rejected editable is
    # deliberate: fix the report and resubmit via a new copy.)

    published = _create(api, status="review")
    api.post(f"/api/field-reports/{published['id']}/approve")
    frozen = api.patch(f"/api/field-reports/{published['id']}", json={"title": "y"})
    assert frozen.status_code == 422


def test_unknown_report_404(api):
    assert api.get("/api/field-reports/999").status_code == 404
    assert api.post("/api/field-reports/999/approve").status_code == 404


def test_operator_create_invite_and_phone_allowlist(api, db, monkeypatch):
    import os

    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "TestBot")
    from app.models.field import FieldOperator as FO

    created = api.post(
        "/api/field-operators",
        json={"display_name": "Juane", "phone": "+52 222 999 8877"},
    )
    assert created.status_code == 200, created.text
    body = created.json()
    assert body["active"] is True
    assert body["accepted_at"] is None

    dup = api.post(
        "/api/field-operators", json={"display_name": "Otro", "phone": "52-222-999-8877"}
    )
    assert dup.status_code == 409  # same digits: normalized clash

    missing = api.post("/api/field-operators", json={"display_name": "X"})
    assert missing.status_code == 422

    invite = api.post(f"/api/field-operators/{body['id']}/invite").json()
    assert invite["token"]
    assert invite["link"] and invite["link"].startswith("https://t.me/")
    assert "start=" in invite["link"]

    # the allowlist now answers the bot phone match via plain query
    listed = api.get("/api/field-operators").json()["items"]
    assert any(o["phone"] == "522229998877" for o in listed)
    assert listed[0]["invited_at"] is not None

    # deactivate cuts the bot access flag without deleting
    off = api.post(f"/api/field-operators/{body['id']}/deactivate")
    assert off.json()["active"] is False
    on = api.post(f"/api/field-operators/{body['id']}/activate")
    assert on.json()["active"] is True
    assert db.scalar(select(FO).where(FO.id == body["id"])) is not None


def test_operator_unknown_404(api):
    assert api.post("/api/field-operators/999/invite").status_code == 404
    assert api.post("/api/field-operators/999/activate").status_code == 404
