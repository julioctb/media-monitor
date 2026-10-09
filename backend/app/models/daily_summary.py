"""DailySummary: one stored digest per client and day (T11).

Exactly one row per (client_id, summary_date); the unique key makes the
daily build idempotent and turns regeneration into a plain UPDATE.
``content`` carries the structured sections (per_source, per_keyword,
silent_keywords, totals) plus a ``plain_text`` render of the whole
summary kept for the future RAG chat. ``narrative`` is the human-facing
paragraph and ``mode`` records the generator that produced it
(heuristic | llm).
"""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPk
from app.models.mention import JsonType

#: Generator modes stored in ``mode``. ``heuristic`` always exists; ``llm``
#: only when the effective settings select an OpenAI-compatible provider.
SUMMARY_MODE_HEURISTIC = "heuristic"
SUMMARY_MODE_LLM = "llm"


class DailySummary(IntPk, Base):
    """The per-client, per-day digest row (T11)."""

    __tablename__ = "daily_summaries"
    __table_args__ = (
        UniqueConstraint("client_id", "summary_date", name="uq_daily_summaries_client_date"),
        Index("ix_daily_summaries_date", "summary_date"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    # Structured sections + content["plain_text"] for the future RAG chat.
    content: Mapped[dict] = mapped_column(JsonType, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<DailySummary id={self.id} client_id={self.client_id} "
            f"date={self.summary_date} mode={self.mode}>"
        )
