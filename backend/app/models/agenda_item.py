"""AgendaItem: a dated (or partially dated) activity on the client agenda.

Production persistence for the agenda page (odd/tasks/agenda-page.md): the
mockup's localStorage was a placeholder. `event_date NULL` means «Sin fecha
completa» — the item renders in the undated bucket until a PATCH promotes
it with a real day. `date_label` keeps the source's partial date string
(«27 oct.») for display; detection/ingest of items is a later phase.
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk

#: Closed kind set, validated at the API edge (mirrors the mockup select).
AGENDA_KINDS = ("activity", "deadline")


class AgendaItem(IntPk, Base):
    __tablename__ = "agenda_items"

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="activity")
    # None = undated («Sin fecha completa»); the edit-date dialog promotes it.
    event_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Source's partial date text, kept for display even after promotion.
    date_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    time_label: Mapped[str | None] = mapped_column(String(16), nullable=True)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    source: Mapped[str | None] = mapped_column(String(200), nullable=True)
    url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    client = relationship("Client")

    def __repr__(self) -> str:
        return f"<AgendaItem id={self.id} client_id={self.client_id} title={self.title!r}>"
