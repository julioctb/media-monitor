"""Scaffold smoke tests: app factory, settings, URL normalization (no DB)."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.db import normalize_database_url
from app.main import create_app


def test_health_endpoint() -> None:
    with TestClient(create_app()) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_settings_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.ingest_interval_min == 15
    assert settings.smtp_port == 587
    assert settings.x_provider_base_url == "https://api.twitterapi.io"


def test_normalize_database_url() -> None:
    assert (
        normalize_database_url("postgres://u:p@h:5432/db")
        == "postgresql+psycopg://u:p@h:5432/db"
    )
    assert (
        normalize_database_url("postgresql://u:p@h:5432/db")
        == "postgresql+psycopg://u:p@h:5432/db"
    )
    assert (
        normalize_database_url("postgresql+psycopg://u:p@h:5432/db")
        == "postgresql+psycopg://u:p@h:5432/db"
    )
