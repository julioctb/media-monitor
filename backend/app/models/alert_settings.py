"""AlertSettings: per-client email alert configuration."""

from sqlalchemy import Boolean, Enum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import AlertChannel, AlertDigest, Base, IntPk


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

    client = relationship("Client", back_populates="alert_settings")

    def __repr__(self) -> str:
        return (
            f"<AlertSettings id={self.id} client_id={self.client_id} "
            f"digest={self.digest}>"
        )
