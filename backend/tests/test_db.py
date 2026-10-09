"""Regression tests for database URL normalization.

Guards the sqlite shorthand healing added after dev-mode alembic crashes
with `sqlite:./dev.db` (single-slash forms are not parseable by
SQLAlchemy's make_url).

Reference forms:
    sqlite:///rel    relative path
    sqlite:////abs   absolute path
"""

from sqlalchemy.engine import make_url

from app.db import normalize_database_url


def test_postgres_driver_aliases() -> None:
    assert (
        normalize_database_url("postgresql://u:p@h:5432/db")
        == "postgresql+psycopg://u:p@h:5432/db"
    )
    assert (
        normalize_database_url("postgres://u:p@h:5432/db")
        == "postgresql+psycopg://u:p@h:5432/db"
    )


def test_sqlite_relative_shorthand_healed() -> None:
    out = normalize_database_url("sqlite:./dev.db")
    assert out == "sqlite:///dev.db"
    make_url(out)  # must parse


def test_sqlite_absolute_shorthand_healed() -> None:
    out = normalize_database_url("sqlite:/data/mediamonitor/dev.db")
    assert out == "sqlite:////data/mediamonitor/dev.db"
    make_url(out)  # must parse


def test_canonical_forms_untouched() -> None:
    assert normalize_database_url("sqlite:///rel.db") == "sqlite:///rel.db"
    assert normalize_database_url("sqlite:////abs.db") == "sqlite:////abs.db"
