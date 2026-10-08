"""Application configuration via environment variables (pydantic-settings)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-driven settings. Variable names map 1:1 to env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "media-monitor"

    # Postgres (plain postgres:// URLs are normalized in app.db)
    database_url: str = "postgresql+psycopg://media:media@localhost:5432/mediamonitor"

    # Client scope for the API and workers (single-tenant MVP; the initial
    # migration seeds client id=1 'default')
    default_client_id: int = 1

    # X/Twitter third-party provider (twitterapi.io-compatible)
    x_provider_api_key: str = ""
    x_provider_base_url: str = "https://api.twitterapi.io"
    # Client-side rate limit for the X provider (requests per minute)
    x_provider_rate_per_min: float = 10.0

    # SMTP for alert emails
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_from: str = "alerts@example.com"

    # Ingest polling interval in minutes
    ingest_interval_min: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
