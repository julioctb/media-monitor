"""ClientSettings: the single per-client configuration row (T9).

One row per client, created lazily on first read (no seed in the
migration). Stored values win at runtime; environment variables only
fill gaps (see app.settings_runtime). Secrets such as ``ai_api_key``
are plaintext in v1 by agreed scope.

The ``mentions.source`` CHECK constraint lives in the mention model /
migration 0002; this module only carries the ai_provider CHECK.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPk
from app.models.mention import JsonType

# Client-facing defaults; mirrored by the 0002 migration server defaults.
DEFAULT_TIMEZONE = "America/Mexico_City"
DEFAULT_RETENTION_DAYS = 365
# Keep in sync with app.sentiment.api_analyzer.DEFAULT_OPENAI_BASE_URL.
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
AI_PROVIDERS = ("local", "openai")


class ClientSettings(IntPk, Base):
    """Runtime configuration for one tenant (exactly one row per client)."""

    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("client_id", name="uq_settings_client"),
        CheckConstraint(
            "ai_provider IN ('local', 'openai')", name="ck_settings_ai_provider"
        ),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    client_name: Mapped[str] = mapped_column(
        String(200), nullable=False, default="", server_default=""
    )
    timezone: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=DEFAULT_TIMEZONE,
        server_default=DEFAULT_TIMEZONE,
    )
    retention_days: Mapped[int] = (
        # 0 disables retention (keep everything); otherwise >= 7 is enforced
        # at validation time (queries.upsert_settings).
        mapped_column(
            Integer,
            nullable=False,
            default=DEFAULT_RETENTION_DAYS,
            server_default="365",
        )
    )
    gdelt_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    facebook_pages: Mapped[list[dict]] = mapped_column(
        JsonType, nullable=False, default=list
    )
    rss_feeds: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    ai_provider: Mapped[str] = (
        # Validated against AI_PROVIDERS; CHECK constraint backs it in DB.
        mapped_column(String(16), nullable=False, default="local", server_default="local")
    )
    ai_api_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_base_url: Mapped[str | None] = mapped_column(
        String(500), nullable=True, server_default=DEFAULT_OPENAI_BASE_URL
    )
    ai_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ai_fallback_local: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    # F2c: max LLM enrichments per ingest cycle; the overflow is backfill work.
    enrich_max_per_cycle: Mapped[int] = mapped_column(
        Integer, nullable=False, default=50, server_default="50"
    )
    # F2c-article-fetch: max article content fetches per ingest cycle.
    fetch_max_per_cycle: Mapped[int] = mapped_column(
        Integer, nullable=False, default=20, server_default="20"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return f"<ClientSettings id={self.id} client_id={self.client_id}>"
