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
    sentiment_shift_enabled: bool = True
    sentiment_shift_threshold: float = 10.0


class AlertSettingsUpdate(BaseModel):
    digest: AlertDigest
    recipient_email: EmailStr
    is_active: bool = True
    # T4 sentiment-shift rule; absent fields keep the stored values.
    sentiment_shift_enabled: bool | None = None
    sentiment_shift_threshold: float | None = Field(default=None, gt=0, le=100)


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


# ----------------------------------------------------------- saved searches


class SavedSearchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    name: str
    query: str
    sources: list[str]
    classifier: str | None
    label: str | None
    range_days: int
    is_active: bool
    created_at: datetime


class SavedSearchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=500)
    sources: list[str] = Field(default_factory=list)
    classifier: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=32)
    range_days: int = Field(default=7, ge=1, le=365)
    is_active: bool = True


class SavedSearchPatch(BaseModel):
    """Partial update; absent fields are kept, empty string clears tags."""

    name: str | None = Field(default=None, max_length=200)
    query: str | None = Field(default=None, max_length=500)
    sources: list[str] | None = None
    classifier: str | None = Field(default=None, max_length=32)
    label: str | None = Field(default=None, max_length=32)
    range_days: int | None = Field(default=None, ge=1, le=365)
    is_active: bool | None = None


class SpikeOut(BaseModel):
    """One spike event for the dashboard timeline."""

    id: int
    saved_search_id: int
    saved_search_name: str
    window_start: datetime
    window_end: datetime
    count: int
    zscore: float
    summary: str | None
    summary_created_at: datetime | None


# ------------------------------------------------------------- daily summaries

# ``date`` as a field name shadows the datetime type inside the class body
# (the default binds before the annotation is evaluated), so the optional
# union is built once here instead of inline.
SummaryDate = date | None


class DailySummaryOut(BaseModel):
    """One stored client-day digest (T11)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    summary_date: date
    content: dict[str, object]
    narrative: str
    mode: str
    created_at: datetime
    updated_at: datetime


class SummaryDayOut(BaseModel):
    """History entry: a stored day and the generator mode that produced it."""

    summary_date: date
    mode: str


class SummaryGenerateRequest(BaseModel):
    """Optional body of POST /summaries/generate; null/absent date = today."""

    date: SummaryDate = None


class IngestRunOut(BaseModel):
    """One ledger row: a single adapter's pass inside an ingest cycle (T3)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    adapter_name: str
    cycle_started: datetime
    status: Literal["ok", "error"]
    items_seen: int
    inserted: int
    error: str | None
    duration_ms: int
    created_at: datetime


class EventOut(BaseModel):
    """Canonical event row (Phase 2): aggregated, no mention drill-down."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    mention_count: int
    source_count: int
    first_seen_at: datetime
    last_seen_at: datetime


class EventMentionOut(BaseModel):
    """Mention stub inside an event detail: enough to rank and link out."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source: MentionSource
    url: str
    title: str | None
    sentiment: Sentiment | None
    published_at: datetime | None


class EventDetailOut(EventOut):
    """Event plus its corroborating mentions, reach-ranked."""

    mentions: list[EventMentionOut]


class EventCoverageRow(BaseModel):
    """Per-source coverage slice of one event."""

    source: MentionSource
    n_mentions: int
    outlets: int


class EventCoverageOut(BaseModel):
    """Which outlets covered an event and how many times each did."""

    event_id: int
    mention_count: int
    outlet_count: int
    by_source: list[EventCoverageRow] = []


class CoverageSummaryDay(BaseModel):
    """One day of client coverage: volume and repetition index."""

    date: date
    events: int
    mentions: int
    multi_source_events: int
    repetition_pct: float
