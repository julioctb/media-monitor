"""AlertSettings: per-client email alert configuration."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AlertChannel, AlertDigest, Base, IntPk

#: Default net-share swing (percentage points) that fires the alert.
DEFAULT_SHIFT_THRESHOLD = 10.0


class AlertSettings(IntPk, Base):
    __tablename__ = "alert_settings"

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[AlertChannel] = mapped_column(
        Enum(
            AlertChannel,
            name="alert_channel",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AlertChannel.email,
    )
    digest: Mapped[AlertDigest] = mapped_column(
        Enum(
            AlertDigest,
            name="alert_digest",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
        default=AlertDigest.instant,
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Alert-engine bookkeeping: watermark of the last digest send and, for
    # digest cadences, when un-notified mentions first appeared.
    last_digest_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    digest_pending_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # T4 sentiment-shift rule: net (positive minus negative) share swing
    # between consecutive windows, in percentage points.
    sentiment_shift_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    sentiment_shift_threshold: Mapped[float] = mapped_column(
        # Numeric on PG via Float? kept Float for sqlite parity; see 0006.
        Float, nullable=False, default=DEFAULT_SHIFT_THRESHOLD, server_default="10"
    )
    sentiment_shift_last_sent: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    client = relationship("Client", back_populates="alert_settings")

    def __repr__(self) -> str:
        return (
            f"<AlertSettings id={self.id} client_id={self.client_id} "
            f"digest={self.digest}>"
        )
