"""Pydantic request/response schemas for the REST API.

NULL sentiment is explicit end to end: `sentiment` is optional on mention
rows, the `none` query filter selects unclassified rows, and the stats
breakdown carries a dedicated "null" bucket.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.ingest.facebook_public import FacebookPageTarget
from app.models import AlertDigest, MentionSource, Sentiment
from app.settings_runtime import parse_digest_hours


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


class PersonRefOut(BaseModel):
    """Mention-card chip: linked person id + canonical name."""

    id: int
    name: str


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
    # F2c enrichment; NULL until the mention is enriched (backfillable).
    summary: str | None
    reach: int | None
    classifications: list[ClassificationOut] = []
    # F3: persons linked via mention_persons; attached batched by the list
    # endpoint (transient attr), never a lazy relationship per row.
    persons: list[PersonRefOut] = []
    # Canonical event context, attached batched by the list endpoint
    # (event_title is a transient attr; event_id comes from the column).
    event_id: int | None = None
    event_title: str | None = None


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
    language: Literal["es", "en", "other"] = "es"

    _normalize = field_validator("text")(_clean_text)


class KeywordUpdate(BaseModel):
    text: str | None = Field(default=None, max_length=500)
    language: Literal["es", "en", "other"] | None = None
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
    by_medium: dict[str, int] = {}
    #: Distinct outlets (hosts) with at least one news mention — the
    #: «Medios con noticias» intro stat; social posts do not count.
    news_medium_count: int = 0
    last_24h: int
    last_7d: int
    daily_volume: list[DailyVolume]
    classifications: list[ClassifierBreakdown] = []


class ToneBucket(BaseModel):
    """Sentiment counts for one home tone-box (the front's ToneCounts)."""

    positive: int = 0
    negative: int = 0
    neutral: int = 0
    unclassified: int = 0
    total: int = 0


class ToneSplit(BaseModel):
    """Home tone boxes per source kind: media / social / field."""

    media: ToneBucket = Field(default_factory=ToneBucket)
    social: ToneBucket = Field(default_factory=ToneBucket)
    field: ToneBucket = Field(default_factory=ToneBucket)


class KeywordDayCount(BaseModel):
    """Mentions of one keyword inside the home-day window."""

    id: int
    text: str
    count: int


class StatsDayOut(BaseModel):
    """GET /stats/day: home-page aggregates for one local day."""

    date: date
    timezone: str
    tones: ToneSplit
    keywords: list[KeywordDayCount]


# ---------------------------------------------------------------- settings


class ClientSettingsOut(BaseModel):
    """Stored settings row (secrets plaintext in v1, by scope)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    client_name: str
    timezone: str
    retention_days: int
    digest_hour: int
    digest_hours: list[int]
    digest_focus_person_id: int | None
    gdelt_enabled: bool
    # Paid-mode X key is masked: x_api_key is ALWAYS "" on the wire; only
    # x_api_key_set tells the UI a key is stored.
    x_mode: Literal["free", "paid"]
    x_api_key: str
    x_api_key_set: bool
    facebook_pages: list[FacebookPageTarget]
    rss_feeds: list[str]
    scrapers: list[str]
    ai_provider: str
    ai_api_key: str | None
    ai_base_url: str | None
    ai_model: str | None
    enrich_max_per_cycle: int
    fetch_max_per_cycle: int
    updated_at: datetime

    @field_validator("digest_hours", mode="before")
    @classmethod
    def _split_digest_hours_csv(cls, value: object) -> object:
        """The column stores a CSV; parse it back to the public int list.

        Already-list values pass through; junk tokens are dropped by the
        shared runtime parser (same tolerance as the worker's read path).
        """
        if isinstance(value, str):
            return parse_digest_hours(value)
        return value

    @field_validator("x_api_key", mode="before")
    @classmethod
    def _mask_x_api_key(cls, value: object) -> str:
        """Never serialize the stored key; the UI reads x_api_key_set."""
        return ""


class ClientSettingsUpdate(BaseModel):
    """Partial update; absent fields are kept, null clears optionals."""

    client_name: str | None = Field(default=None, max_length=200)
    timezone: str | None = None
    retention_days: int | None = Field(default=None, ge=0)
    digest_hour: int | None = Field(default=None, ge=0, le=23)
    digest_hours: list[int] | None = Field(default=None)
    digest_focus_person_id: int | None = Field(default=None, ge=1)
    gdelt_enabled: bool | None = None
    # X source mode; x_api_key: non-empty stores, ''/null keeps the stored
    # key (the GET never returns it, so the masked UI sends '' to keep).
    x_mode: Literal["free", "paid"] | None = None
    x_api_key: str | None = Field(default=None, max_length=500)
    facebook_pages: list[FacebookPageTarget] | None = None
    rss_feeds: list[str] | None = None
    scrapers: list[str] | None = None
    ai_provider: Literal["local", "openai"] | None = None
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    enrich_max_per_cycle: int | None = Field(default=None, ge=1, le=1000)
    fetch_max_per_cycle: int | None = Field(default=None, ge=1, le=1000)

    @field_validator("digest_hours")
    @classmethod
    def _check_digest_hours(cls, value: list[int] | None) -> list[int] | None:
        """1..8 hours in 0..23; storage normalizes to a sorted CSV."""
        if value is None:
            return None
        if not 1 <= len(value) <= 8:
            raise ValueError("digest_hours needs between 1 and 8 hours")
        for hour in value:
            if isinstance(hour, bool) or not isinstance(hour, int) or not 0 <= hour <= 23:
                raise ValueError("digest_hours hours must be integers between 0 and 23")
        return value


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


class SummaryRevisionOut(BaseModel):
    """One stored narrative revision (append-only build history)."""

    model_config = ConfigDict(from_attributes=True)

    seq: int
    summary_date: date
    narrative: str
    mode: str
    created_at: datetime


class SummaryRevisionDayOut(BaseModel):
    """Index row: a day with stored revisions and how many."""

    summary_date: date
    count: int
    last_at: datetime


class SummaryRevisionRestoreRequest(BaseModel):
    """Body of POST /summary-revisions/restore."""

    day: date
    seq: int


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
    # F2c: LLM synthesis over mention summaries; title while a lone mention.
    summary: str | None
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


# ---------------------------------------------------------------- persons (F3)


class PersonOut(BaseModel):
    """Person row with its denormalized mention count."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_key: str
    role: str | None
    org: str | None
    aliases: list[str] = []
    first_seen_at: datetime
    last_seen_at: datetime
    mention_count: int


class PersonTimelineItem(BaseModel):
    """One mention of the person: quote, source and context (F3 exit gate)."""

    model_config = ConfigDict(from_attributes=True)

    mention_id: int
    title: str | None
    url: str
    source: MentionSource
    published_at: datetime | None
    ingested_at: datetime
    sentiment: Sentiment | None
    role: str | None
    org: str | None
    context: str | None
    event_id: int | None
    event_title: str | None
    political_label: str | None


class PersonDetailOut(PersonOut):
    timeline: list[PersonTimelineItem] = []


class AskCitationOut(BaseModel):
    """One context mention backing the answer, linkable in the UI."""

    mention_id: int
    title: str | None
    url: str
    source: MentionSource
    published_at: str
    sentiment: Sentiment | None


class AskResponse(BaseModel):
    answer: str
    citations: list[AskCitationOut] = []
    person: dict | None = None
    matched_mentions: int = 0


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


# ---------------------------------------------------------------- agenda


class AgendaItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    client_id: int
    title: str
    kind: str
    event_date: date | None
    date_label: str | None
    time_label: str | None
    location: str | None
    source: str | None
    url: str | None
    notes: str | None
    created_at: datetime


class AgendaItemCreate(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    kind: str = "activity"
    event_date: date | None = None
    date_label: str | None = Field(default=None, max_length=64)
    time_label: str | None = Field(default=None, max_length=16)
    location: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    notes: str | None = None


class AgendaItemPatch(BaseModel):
    """Partial update; the edit-date dialog sends only `event_date`."""

    title: str | None = Field(default=None, min_length=1, max_length=240)
    kind: str | None = None
    event_date: date | None = None
    date_label: str | None = Field(default=None, max_length=64)
    time_label: str | None = Field(default=None, max_length=16)
    location: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=200)
    url: str | None = Field(default=None, max_length=500)
    notes: str | None = None
