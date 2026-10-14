"""Event: canonical cluster of mentions covering the same fact.

Built deterministically at ingest time (token-Jaccard over titles inside a
48h window, app.ingest.events). An event never crosses client_id; the
canonical title is the longest seen so far and the counters are recomputed
on every assignment (app.ingest.events.touch_event).
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk


class Event(IntPk, Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_client_first_seen", "client_id", "first_seen_at"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    # Canonical: longest title seen among the grouped mentions.
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    # Folded token string, kept for debugging/inspection (not queried yet).
    title_tokens: Mapped[str] = mapped_column(String(500), nullable=False)
    mention_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    client = relationship("Client", back_populates="events")
    mentions: Mapped[list["Mention"]] = relationship(back_populates="event")  # noqa: F821

    def __repr__(self) -> str:
        return f"<Event id={self.id} client_id={self.client_id} mentions={self.mention_count}>"
