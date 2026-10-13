"""IngestCursor: per-adapter ingest watermark (T1).

One row per (client, adapter). `last_success_at` is the cycle-start
timestamp of the last clean adapter pass; the pipeline advances it ONLY
on success, so a failing source accumulates visible debt instead of
silently re-scanning the same window forever. `overlap_min` re-fetches
a safety margin before the watermark to catch boundary items.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPk


class IngestCursor(IntPk, Base):
    """Durable ingest watermark for one (client, adapter) pair."""

    __tablename__ = "ingest_cursors"
    __table_args__ = (
        UniqueConstraint("client_id", "adapter_name", name="uq_ingest_cursors_pair"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    adapter_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # NULL until the adapter's first successful cycle.
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    overlap_min: Mapped[int] = mapped_column(Integer, nullable=False, default=15)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<IngestCursor id={self.id} client_id={self.client_id} "
            f"adapter={self.adapter_name!r} "
            f"last_success_at={self.last_success_at}>"
        )
