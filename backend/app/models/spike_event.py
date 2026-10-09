"""SpikeEvent: an anomalous hourly mention count for a saved search (T2).

Rows are written only by app.spike.scan (worker `spike_scan_job`); the
unique (saved_search, window_start) key makes scans idempotent — reruns
never duplicate an event.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk


class SpikeEvent(IntPk, Base):
    __tablename__ = "spike_events"
    __table_args__ = (
        UniqueConstraint(
            "saved_search_id", "window_start", name="uq_spike_events_search_window"
        ),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    saved_search_id: Mapped[int] = mapped_column(
        ForeignKey("saved_searches.id", ondelete="CASCADE"), nullable=False
    )
    # Hour bucket the anomaly was detected in; window_end is exclusive.
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_mean: Mapped[float] = mapped_column(Float, nullable=False)
    baseline_stddev: Mapped[float] = mapped_column(Float, nullable=False)
    zscore: Mapped[float] = mapped_column(Float, nullable=False)

    # T3: AI summary of the spike window; NULL until generated (or when no
    # provider is configured — alerting degrades, never raises).
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    saved_search = relationship("SavedSearch", back_populates="spike_events")

    def __repr__(self) -> str:
        return (
            f"<SpikeEvent id={self.id} saved_search_id={self.saved_search_id} "
            f"window_start={self.window_start:%Y-%m-%d %H:%M} count={self.count}>"
        )
