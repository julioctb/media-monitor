"""Tests for agenda auto-detection from digest content (agenda-detect).

Contract: ``sync_agenda_from_digest`` turns ``content.agenda`` entries
(``when``+``title`` required, ``status``/``source`` optional) into
``agenda_items`` rows, idempotently — a second run over the same digest
creates nothing. Date parsing is best-effort Spanish («27 oct.»); unparsable
dates stay undated («Sin fecha completa»). Kind heuristic: inscription
wording -> ``deadline``, else ``activity``.
"""

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Client
from app.summaries.agenda_detect import (
    detect_kind,
    normalize_title,
    parse_spanish_date,
    sync_agenda_from_digest,
)


@pytest.fixture()
def db(tmp_path):
    """Fresh SQLite database per test (same shape as test_api)."""
    engine = create_engine(f"sqlite:///{tmp_path}/agenda_detect.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    yield session
    session.close()
    engine.dispose()


def test_parse_spanish_date_variants() -> None:
    assert parse_spanish_date("27 oct.", 2026) == date(2026, 10, 27)
    assert parse_spanish_date("15 noviembre", 2026) == date(2026, 11, 15)
    assert parse_spanish_date("2 de diciembre de 2027", 2026) == date(2027, 12, 2)
    assert parse_spanish_date("2026-11-02", 2026) == date(2026, 11, 2)
    assert parse_spanish_date("Hasta el 15 nov.", 2026) == date(2026, 11, 15)
    # Ambiguous/unparseable -> None (caller keeps the raw label).
    assert parse_spanish_date("próxima semana", 2026) is None
    assert parse_spanish_date("", 2026) is None


def test_detect_kind_heuristic() -> None:
    assert detect_kind("Inscripciones para «Bestias Eternas»", None) == "deadline"
    assert detect_kind("Taller", "cierre de inscripciones") == "deadline"
    assert detect_kind("Conectados pero solos", "plática") == "activity"


def test_normalize_title_folds_accents_and_case() -> None:
    assert normalize_title("Taller de Cáncer de Mama") == normalize_title(
        "taller de cancer de mama "
    )


def test_sync_rolls_past_dates_to_next_occurrence(db) -> None:
    """«15 nov.» detected on Dec 28 must land in Nov 2027, not the past."""

    db.add(Client(name="acme"))
    db.commit()
    client_id = db.query(Client).order_by(Client.id).first().id
    reference = date(2026, 12, 28)
    content = {
        "agenda": [
            # Same year, ahead of the reference: stays.
            {"when": "30 dic.", "title": "Evento año actual"},
            # Before the reference: next occurrence.
            {"when": "15 nov.", "title": "Edición próxima"},
            # Explicit year wins over the roll.
            {"when": "10 de enero de 2026", "title": "Fecha explícita pasada"},
        ]
    }

    created = sync_agenda_from_digest(db, client_id, content, reference=reference)
    assert created == 3

    from app.models import queries

    by_title = {r.title: r for r in queries.list_agenda_items(db, client_id)}
    assert by_title["Evento año actual"].event_date == date(2026, 12, 30)
    assert by_title["Edición próxima"].event_date == date(2027, 11, 15)
    # Explicit years roll too: past = next occurrence, uniform rule.
    assert by_title["Fecha explícita pasada"].event_date == date(2027, 1, 10)


def test_sync_creates_dedupes_and_keeps_unparsed_dates(db) -> None:
    db.add(Client(name="acme"))
    db.commit()
    client_id = db.query(Client).order_by(Client.id).first().id
    content = {
        "agenda": [
            {"when": "27 oct.", "title": "Taller de cáncer de mama", "source": "X"},
            {"when": "Hasta el 15 nov.", "title": "Inscripciones Bestias Eternas", "status": "cierre"},
            {"when": "próxima semana", "title": "Sin fecha clara"},
        ]
    }

    created = sync_agenda_from_digest(db, client_id, content, reference=date(2026, 10, 23))
    assert created == 3

    from app.models import queries

    rows = queries.list_agenda_items(db, client_id)
    assert [r.title for r in rows] == [
        "Taller de cáncer de mama",
        "Inscripciones Bestias Eternas",
        "Sin fecha clara",
    ]
    # 27 oct within the digest year; the deadline parsed its day; the
    # unparseable one stays undated with the label preserved.
    assert rows[0].event_date == date(2026, 10, 27)
    assert rows[0].kind == "activity"
    assert rows[1].event_date == date(2026, 11, 15)
    assert rows[1].kind == "deadline"
    assert rows[2].event_date is None
    assert rows[2].date_label == "próxima semana"

    # Idempotent: same digest again -> nothing new.
    again = sync_agenda_from_digest(db, client_id, content, reference=date(2026, 10, 23))
    assert again == 0
    assert len(queries.list_agenda_items(db, client_id)) == 3


def _client_id(db) -> int:
    db.add(Client(name="acme"))
    db.commit()
    return db.query(Client).order_by(Client.id).first().id


def test_sync_dedupes_near_titles_on_the_same_day(db) -> None:
    """F2a: mismo día + Jaccard >= 0.6 = un solo compromiso, no dos filas."""
    client_id = _client_id(db)
    content = {
        "agenda": [
            {"when": "28 oct.", "title": "Paro activo en la BUAP"},
            {"when": "28 de octubre", "title": "Paro activo BUAP"},
        ]
    }

    created = sync_agenda_from_digest(db, client_id, content, reference=date(2026, 10, 24))
    assert created == 1

    from app.models import queries

    rows = queries.list_agenda_items(db, client_id)
    assert [r.title for r in rows] == ["Paro activo en la BUAP"]
    assert rows[0].event_date == date(2026, 10, 28)

    # Idempotencia reforzada: un regen con el título parafraseado no suma.
    again = sync_agenda_from_digest(db, client_id, content, reference=date(2026, 10, 24))
    assert again == 0


def test_sync_keeps_near_titles_on_different_days(db) -> None:
    client_id = _client_id(db)
    content = {
        "agenda": [
            {"when": "28 oct.", "title": "Paro activo en la BUAP"},
            {"when": "29 oct.", "title": "Paro activo BUAP"},
        ]
    }

    created = sync_agenda_from_digest(db, client_id, content, reference=date(2026, 10, 24))
    assert created == 2


def test_sync_near_dupe_needs_a_parsed_date(db) -> None:
    """Sin fecha parseable no hay cruce: la near-dup no descarta nada."""
    client_id = _client_id(db)
    content = {
        "agenda": [
            {"when": "próxima semana", "title": "Paro activo en la BUAP"},
            {"when": "fecha por confirmar", "title": "Paro activo BUAP"},
        ]
    }

    created = sync_agenda_from_digest(db, client_id, content, reference=date(2026, 10, 24))
    assert created == 2
