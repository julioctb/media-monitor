"""Client: the tenant entity. Every domain row carries a client_id."""

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk


class Client(IntPk, Base):
    __tablename__ = "clients"

    name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    keywords = relationship(
        "Keyword", back_populates="client", cascade="all, delete-orphan"
    )
    mentions = relationship(
        "Mention", back_populates="client", cascade="all, delete-orphan"
    )
    alert_settings = relationship(
        "AlertSettings", back_populates="client", cascade="all, delete-orphan"
    )
    saved_searches = relationship(
        "SavedSearch", back_populates="client", cascade="all, delete-orphan"
    )
    events = relationship("Event", back_populates="client", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Client id={self.id} name={self.name!r}>"
