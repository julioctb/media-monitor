"""Pydantic request/response schemas for the REST API.

NULL sentiment is explicit end to end: `sentiment` is optional on mention
rows, the `none` query filter selects unclassified rows, and the stats
breakdown carries a dedicated "null" bucket.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.ingest.facebook_page import FacebookPageCredentials
from app.models import AlertDigest, MentionSource, Sentiment


def _clean_text(value: str | None) -> str | None:
    """Strip keyword text; empty-after-strip is a validation error."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("text must not be empty")
    return value


class ClassificationOut(BaseModel):
    """One classifier's stored label for a mention."""

    model_config = ConfigDict(from_attributes=True)

    classifier: str
    label: str
    score: float


class MentionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    keyword_id: int | None
    source: MentionSource
    external_id: str | None
    url: str
    title: str | None
    content: str | None
    author: str | None
    lang: str | None
    published_at: datetime | None
    ingested_at: datetime
    sentiment: Sentiment | None
    sentiment_score: float | None
    reach: int | None
    classifications: list[ClassificationOut] = []


class MentionPage(BaseModel):
    items: list[MentionOut]
    total: int


class KeywordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    text: str
    language: str
    is_active: bool
    created_at: datetime


class KeywordCreate(BaseModel):
    text: str = Field(max_length=500)
    language: Literal["es", "en"] = "es"

    _normalize = field_validator("text")(_clean_text)


class KeywordUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    language: Literal["es", "en"] | None = None
    is_active: bool | None = None

    _normalize = field_validator("text")(_clean_text)


class AlertSettingsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    digest: AlertDigest
    recipient_email: str | None
    is_active: bool


class AlertSettingsUpdate(BaseModel):
    digest: AlertDigest
    recipient_email: EmailStr
    is_active: bool = True


class DailyVolume(BaseModel):
    date: date
    count: int


class ClassifierBreakdown(BaseModel):
    """Aggregates for one classifier: total rows and count per label."""

    classifier: str
    total_classified: int
    breakdown: dict[str, int]


class StatsOverview(BaseModel):
    total: int
    by_sentiment: dict[str, int]
    by_source: dict[str, int]
    last_24h: int
    last_7d: int
    daily_volume: list[DailyVolume]
    classifications: list[ClassifierBreakdown] = []


# ---------------------------------------------------------------- settings


class ClientSettingsOut(BaseModel):
    """Stored settings row (secrets plaintext in v1, by scope)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    client_name: str
    timezone: str
    retention_days: int
    gdelt_enabled: bool
    facebook_pages: list[FacebookPageCredentials]
    rss_feeds: list[str]
    ai_provider: str
    ai_api_key: str | None
    ai_base_url: str | None
    ai_model: str | None
    ai_fallback_local: bool
    updated_at: datetime


class ClientSettingsUpdate(BaseModel):
    """Partial update; absent fields are kept, null clears optionals."""

    client_name: str | None = Field(default=None, max_length=200)
    timezone: str | None = None
    retention_days: int | None = Field(default=None, ge=0)
    gdelt_enabled: bool | None = None
    facebook_pages: list[FacebookPageCredentials] | None = None
    rss_feeds: list[str] | None = None
    ai_provider: Literal["local", "openai"] | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    ai_fallback_local: bool | None = None


class FacebookProbeRequest(BaseModel):
    page_id: str = Field(min_length=1)
    token: str = Field(min_length=1)


class AiProbeRequest(BaseModel):
    provider: Literal["local", "openai"] = "local"
    api_key: str | None = None
    base_url: str | None = None
    model: str | None = None
