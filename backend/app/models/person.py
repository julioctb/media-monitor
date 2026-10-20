"""Person: deduplicated entity extracted from mention enrichments (F3).

Identity: (client_id, name_key) where name_key is the fold_text form of the
canonical name — accents and case folded, so "Xóchitl Gálvez" and "xochitl
galvez resolve to one row. Variants seen in the wild live in ``aliases``
(raw strings) and ``alias_keys`` (space-joined folded forms, kept so the
list endpoint can search aliases in plain SQL). Resolution happens ONLY
through app.persons.resolve_person; nothing writes Person rows directly.

MentionPerson is the per-mention occurrence: role/org as extracted on that
mention, ``context`` carrying the verbatim quote when the article prints
one, and the stance pair (stance_target_id + stance_polarity) reserved for
the structured stance modeling from the plan — the raw stance string stays
in mentions.raw_enrichment.
"""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING, Any

from app.models.base import Base, IntPk

if TYPE_CHECKING:
    from app.models.mention import Mention

# JSON on SQLite (tests), JSONB on PostgreSQL (production) — same variant
# pattern as mentions.raw_enrichment.
JsonType = JSON().with_variant(JSONB(), "postgresql")


class Person(IntPk, Base):
    __tablename__ = "persons"
    __table_args__ = (
        UniqueConstraint("client_id", "name_key", name="uq_persons_client_name_key"),
        Index("ix_persons_client_last_seen", "client_id", "last_seen_at"),
    )

    client_id: Mapped[int] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    # Canonical display form: longest/cleanest variant seen so far.
    name: Mapped[str] = mapped_column(String(500), nullable=False)
    # fold_text(name): the dedupe key, unique per client.
    name_key: Mapped[str] = mapped_column(String(500), nullable=False)
    # Raw alias variants (unfolded), for display and audit.
    aliases: Mapped[list[Any]] = mapped_column(JsonType, nullable=False, default=list)
    # Comma-joined fold_text of every alias: alias search via plain LIKE.
    # Comma, not space: folded names contain spaces.
    alias_keys: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Latest known role/org; filled on first sight, kept afterwards.
    role: Mapped[str | None] = mapped_column(String(500), nullable=True)
    org: Mapped[str | None] = mapped_column(String(500), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    mention_links: Mapped[list["MentionPerson"]] = relationship(
        "MentionPerson",
        back_populates="person",
        cascade="all, delete-orphan",
        passive_deletes=True,
        foreign_keys="MentionPerson.person_id",  # noqa: F821
    )

    def __repr__(self) -> str:
        return f"<Person id={self.id} client_id={self.client_id} name={self.name!r}>"


class MentionPerson(IntPk, Base):
    __tablename__ = "mention_persons"
    __table_args__ = (
        UniqueConstraint("mention_id", "person_id", name="uq_mention_person"),
        Index("ix_mention_person_person", "person_id"),
        Index("ix_mention_person_mention", "mention_id"),
    )

    mention_id: Mapped[int] = mapped_column(
        ForeignKey("mentions.id", ondelete="CASCADE"), nullable=False
    )
    person_id: Mapped[int] = mapped_column(
        ForeignKey("persons.id", ondelete="CASCADE"), nullable=False
    )
    # As extracted on THIS mention; Person.role/org holds the aggregated view.
    role: Mapped[str | None] = mapped_column(String(500), nullable=True)
    org: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Verbatim quote / statement when the source text carries one.
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Structured stance (plan F3-A): who this stance is about and its
    # polarity; nullable until the stance modeling lands.
    stance_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("persons.id", use_alter=True, ondelete="SET NULL"), nullable=True
    )
    stance_polarity: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    mention: Mapped["Mention"] = relationship(  # noqa: F821
        "Mention", back_populates="person_links"
    )
    person: Mapped["Person"] = relationship(  # noqa: F821
        back_populates="mention_links", foreign_keys=[person_id]
    )

    def __repr__(self) -> str:
        return (
            f"<MentionPerson id={self.id} mention_id={self.mention_id} "
            f"person_id={self.person_id}>"
        )
