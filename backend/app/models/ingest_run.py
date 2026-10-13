"""IngestRun: ledger row per adapter per cycle (T3).

Written by app.ingest.pipeline at the end of every adapter pass: status
ok|error, items seen, inserted count, exception text and duration. The
ledger is what makes "sin noticias" distinguishable from "fuente caída"
and turns a failing source into visible, queryable debt.
"""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IntPk


class IngestRun(IntPk, Base):
    """One ingest attempt of one adapter inside one cycle."""

    __tablename__ = "ingest_runs"
    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error')", name="ck_ingest_runs_status"),
        Index("ix_ingest_runs_client_started", "client_id", "cycle_started"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    adapter_name: Mapped[str] = mapped_column(String(64), nullable=False)
    # Cycle start shared by every adapter row of the same pass.
    cycle_started: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ok")
    items_seen: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    inserted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Exception text when status == error; NULL on success.
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<IngestRun id={self.id} adapter={self.adapter_name!r} "
            f"status={self.status} inserted={self.inserted}>"
        )
