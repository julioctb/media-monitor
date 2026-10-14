"""Shared pytest fixtures: in-memory SQLite database (no Postgres needed)."""

import pytest
from sqlalchemy.orm import Session, sessionmaker

from sqlalchemy import create_engine

from app.models import Base


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


@pytest.fixture()
def fresh_laya():
    """Reset the process-wide lazy laya singleton around the test."""
    from app.sentiment import factory

    saved = factory._laya_singleton
    factory._laya_singleton = None
    try:
        yield factory.shared_laya()
    finally:
        factory._laya_singleton = saved
