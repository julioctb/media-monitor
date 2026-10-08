"""Mention: a single brand mention ingested from any source.

Dedupe key: url_hash (sha256 of the normalized URL), unique across the table.
Ingest adapters MUST build mentions through app.models.queries.insert_mention
so client scoping and url_hash computation stay consistent.
"""

import hashlib
from datetime import datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk, MentionSource, Sentiment

# JSON on SQLite (tests), JSONB on PostgreSQL (production).
JsonType = JSON().with_variant(JSONB(), "postgresql")


# Tracking params stripped alongside utm_* during URL normalization.
_TRACKING_PARAMS = frozenset({"fbclid", "gclid"})


def normalize_url(url: str) -> str:
    """Canonicalize a URL for hashing: lowercase scheme/host, drop fragment,
    drop trailing slash and utm_*/fbclid/gclid tracking params, sort query."""
    parts = urlsplit(url.strip())
    query = urlencode(
        sorted(
            (k, v)
            for k, v in parse_qsl(parts.query)
            if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
        )
    )
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ""))


def make_url_hash(url: str) -> str:
    """Stable dedupe key for a mention URL (sha256 hex of the normalized URL)."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


class Mention(IntPk, Base):
    __tablename__ = "mentions"
    __table_args__ = (
        Index("ix_mentions_client_published", "client_id", "published_at"),
        Index("ix_mentions_client_source", "client_id", "source"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    keyword_id: Mapped[int | None] = mapped_column(
        ForeignKey("keywords.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[MentionSource] = mapped_column(
        Enum(
            MentionSource,
            name="mention_source",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    external_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    url_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sentiment: Mapped[Sentiment | None] = mapped_column(
        Enum(
            Sentiment,
            name="sentiment",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reach: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JsonType, nullable=True)

    client = relationship("Client", back_populates="mentions")
    keyword = relationship("Keyword", back_populates="mentions")

    def __repr__(self) -> str:
        return f"<Mention id={self.id} client_id={self.client_id} source={self.source}>"
