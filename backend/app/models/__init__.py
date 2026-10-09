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
from app.models.client import Client
from app.models.keyword import Keyword
from app.models.mention import Mention, make_url_hash, normalize_url
from app.models.settings import ClientSettings
from app.models import queries

__all__ = [
    "AlertChannel",
    "AlertDigest",
    "AlertSettings",
    "Base",
    "Client",
    "ClientSettings",
    "Keyword",
    "Mention",
    "MentionSource",
    "Sentiment",
    "make_url_hash",
    "normalize_url",
    "queries",
]
