"""Field reports: the human channel of the feed.

Operators in the territory report via the field bot (Telegram; intake
guided, never free-form). Everything in this domain is prefixed ``field_``
and kept in this module so extraction into its own service stays a
file-move, per the field-reports design decision.

Lifecycle: ``draft`` (bot conversation in progress) -> ``review`` (waiting
for human approval; manual submissions may land here directly) ->
``published`` (a Mention with source ``field_report`` is created and linked)
or ``rejected`` (terminal, with ``review_note``). The LLM enrichment step
(much later) only writes suggestions; it never moves state.
"""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.models.base import Base, IntPk

#: JSON on SQLite (tests), JSONB on PostgreSQL (production) — same variant
#: rule as Mention.raw.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class FieldReportStatus:
    """Plain-string status; a class const over an Enum to stay table-check
    friendly (mirrors daily_summary_revisions.mode)."""

    DRAFT = "draft"
    REVIEW = "review"
    PUBLISHED = "published"
    REJECTED = "rejected"

    ALL = (DRAFT, REVIEW, PUBLISHED, REJECTED)


class FieldOperator(IntPk, Base):
    __tablename__ = "field_operators"

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    #: Telegram user id once the bot phase lands; nullable until then so
    # manual/seeded operators exist from day one.
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    __table_args__ = (
        # One identity per messaging account per client.
        Index("uq_field_operators_client_tg", "client_id", "telegram_user_id",
              unique=True),
    )


class FieldReport(IntPk, Base):
    __tablename__ = "field_reports"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'review', 'published', 'rejected')",
            name="ck_field_reports_status",
        ),
        Index("ix_field_reports_client_status", "client_id", "status"),
        Index("ix_field_reports_client_created", "client_id", "created_at"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    operator_id: Mapped[int | None] = mapped_column(
        ForeignKey("field_operators.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=FieldReportStatus.DRAFT)

    # --- intake (guided answers, verbatim) ---
    place: Mapped[str | None] = mapped_column(String(500), nullable=True)
    happened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Raw intake payload (question -> answer); audit trail of the bot phase.
    intake: Mapped[dict | None] = mapped_column(JsonType, nullable=True)

    # --- publishable shape (normalized; review may edit) ---
    title: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)

    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: LLM suggestions (title/summary/tone/duplicate); never state.
    enrichment: Mapped[dict | None] = mapped_column(JsonType, nullable=True)
    mention_id: Mapped[int | None] = mapped_column(
        ForeignKey("mentions.id", ondelete="SET NULL"), nullable=True, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
