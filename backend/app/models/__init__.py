"""Domain model package. Import models from here so SQLAlchemy resolves
relationships and Alembic's env.py sees the full metadata."""

from app.models.alert_settings import AlertSettings
from app.models.base import (
    AlertChannel,
    AlertDigest,
    Base,
    MentionSource,
    Sentiment,
)
from app.models.classification import MentionClassification
from app.models.client import Client
from app.models.daily_summary import DailySummary
from app.models.event import Event
from app.models.ingest_cursor import IngestCursor
from app.models.ingest_run import IngestRun
from app.models.keyword import Keyword
from app.models.mention import Mention, make_url_hash, normalize_url
from app.models.person import MentionPerson, Person
from app.models.saved_search import SavedSearch
from app.models.settings import ClientSettings
from app.models.spike_event import SpikeEvent
from app.models import queries

__all__ = [
    "AlertChannel",
    "AlertDigest",
    "AlertSettings",
    "Base",
    "Client",
    "ClientSettings",
    "DailySummary",
    "Event",
    "IngestCursor",
    "IngestRun",
    "Keyword",
    "Mention",
    "MentionClassification",
    "MentionPerson",
    "MentionSource",
    "Person",
    "SavedSearch",
    "Sentiment",
    "SpikeEvent",
    "make_url_hash",
    "normalize_url",
    "queries",
]
