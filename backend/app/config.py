"""Application configuration via environment variables (pydantic-settings)."""

import json
from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from app.ingest.facebook_public import FacebookPageTarget


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

    # X/Twitter paid provider defaults (twitterapi.io-compatible): the API
    # key is NOT env-driven anymore — it lives in settings (x_api_key) and
    # the worker wires the provider from there (x_mode='paid').
    x_provider_base_url: str = "https://api.twitterapi.io"
    # Client-side rate limit for the X provider (requests per minute)
    x_provider_rate_per_min: float = 10.0

    # Public Facebook pages: JSON list of {"page_id", "label"} (id numeric
    # or slug). Empty/unset disables the adapter; no tokens — the public
    # HTML is scraped headless.
    fb_pages: Annotated[list[FacebookPageTarget], NoDecode] = Field(
        default_factory=list
    )

    # SMTP for alert emails
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_from: str = "alerts@example.com"

    # Ingest polling interval in minutes
    ingest_interval_min: int = 15

    @field_validator("fb_pages", mode="before")
    @classmethod
    def _parse_fb_pages(cls, value: object) -> object:
        """Accept a JSON array; an empty env value means disabled.

        NoDecode keeps the raw string away from pydantic-settings' own
        JSON decoding, which would choke on '' (the usual `FB_PAGES=`
        line in .env files).
        """
        if value is None or (isinstance(value, str) and not value.strip()):
            return []
        if isinstance(value, str):
            return json.loads(value)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
