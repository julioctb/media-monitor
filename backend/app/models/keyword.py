"""Keyword: a brand term tracked for a client, with language tag."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk


class Keyword(IntPk, Base):
    __tablename__ = "keywords"
    __table_args__ = (
        UniqueConstraint("client_id", "text", name="uq_keywords_client_text"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    language: Mapped[str] = mapped_column(String(8), nullable=False, default="es")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    client = relationship("Client", back_populates="keywords")
    mentions = relationship("Mention", back_populates="keyword")

    def __repr__(self) -> str:
        return f"<Keyword id={self.id} client_id={self.client_id} text={self.text!r}>"
