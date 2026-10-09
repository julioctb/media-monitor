"""SavedSearch: a persisted client query feeding spikes and alerts (T1).

A saved search is only a stored filter bundle (query text, sources,
classifier/label probe); it never ingests anything. Every consumer must
resolve mention sets through app.models.queries (saved_search_filters ->
_mention_filters) so tenant scoping stays in one place.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk
from app.models.mention import JsonType


class SavedSearch(IntPk, Base):
    __tablename__ = "saved_searches"
    __table_args__ = (
        UniqueConstraint("client_id", "name", name="uq_saved_searches_client_name"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Free-text probe matched (case-insensitive) against title/content,
    # exactly like the `q` filter on the mention feed.
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    # Empty list = every source; otherwise a subset of MentionSource values.
    sources: Mapped[list[str]] = mapped_column(JsonType, nullable=False, default=list)
    classifier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Default date range offered in the UI (days back from now).
    range_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7, server_default="7")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    client = relationship("Client", back_populates="saved_searches")

    def __repr__(self) -> str:
        return (
            f"<SavedSearch id={self.id} client_id={self.client_id} "
            f"name={self.name!r}>"
        )
