"""Audit of event-identity arbitrations (event-identity T2b).

One row per adjudicated pair, both verdicts: `misma` pairs were merged
(the `event_from` event was deleted), `distinta` pairs stay split. The
table is the memo that keeps the arbiter from re-asking the same pair
every cycle, and the review surface for undoing a wrong merge.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPk


class EventMerge(IntPk, Base):
    __tablename__ = "event_merges"
    __table_args__ = (
        # The pair-skip lookup scans by client, newest first.
        Index("ix_event_merges_client_created", "client_id", "created_at"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    # Plain ints on purpose: `event_from` is deleted by the merge itself, an
    # FK there would cascade-break the audit row.
    event_from: Mapped[int] = mapped_column(Integer, nullable=False)
    event_to: Mapped[int] = mapped_column(Integer, nullable=False)
    # Best lexical score of the pair at arbitration time.
    score: Mapped[float] = mapped_column(Float, nullable=False)
    # `misma` | `distinta` — the arbiter's verdict.
    verdict: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    # Model that judged (ai_model_fast fallback chain, for the record).
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<EventMerge {self.event_from}->{self.event_to} "
            f"{self.verdict} score={self.score:.3f}>"
        )
