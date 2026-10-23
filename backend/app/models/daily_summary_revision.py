"""DailySummaryRevision: append-only narrative history per client/day.

Every digest build (worker cut or API regen) stores the narrative it
produced BEFORE overwriting the live row, so no prose is ever lost: the
latest revision mirrors ``daily_summaries`` and older ones allow compare
and restore. Failure to log never fails the digest (same contract as the
agenda hook).
"""

from datetime import date, datetime

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPk


class DailySummaryRevision(IntPk, Base):
    """One immutable narrative snapshot of a digest build."""

    __tablename__ = "daily_summary_revisions"
    __table_args__ = (
        UniqueConstraint(
            "client_id", "summary_date", "seq", name="uq_summary_revisions_client_day_seq"
        ),
        Index("ix_summary_revisions_day", "client_id", "summary_date"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    summary_date: Mapped[date] = mapped_column(Date, nullable=False)
    # 1..n per (client, day), in build order.
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    narrative: Mapped[str] = mapped_column(Text, nullable=False)

    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
