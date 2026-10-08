"""Pydantic request/response schemas for the REST API.

NULL sentiment is explicit end to end: `sentiment` is optional on mention
rows, the `none` query filter selects unclassified rows, and the stats
breakdown carries a dedicated "null" bucket.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.models import AlertDigest, MentionSource, Sentiment


def _clean_text(value: str | None) -> str | None:
    """Strip keyword text; empty-after-strip is a validation error."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("text must not be empty")
    return value


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


class StatsOverview(BaseModel):
    total: int
    by_sentiment: dict[str, int]
    by_source: dict[str, int]
    last_24h: int
    last_7d: int
    daily_volume: list[DailyVolume]
