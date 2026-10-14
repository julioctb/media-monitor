"""Persons and mention_persons: F3 deduplicated entities + per-mention links.

Persons are resolved from mentions.raw_enrichment (persons already extracted
by the enrichment pass — no new L calls); identity is (client_id, name_key)
with name_key = fold_text(name). Backfill: scripts/backfill_persons.

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "persons",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=500), nullable=False),
        sa.Column("name_key", sa.String(length=500), nullable=False),
        sa.Column("aliases", JSONB(), nullable=False),
        sa.Column("alias_keys", sa.Text(), nullable=False),
        sa.Column("role", sa.String(length=500), nullable=True),
        sa.Column("org", sa.String(length=500), nullable=True),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name_key", name="uq_persons_client_name_key"),
    )
    op.create_index(
        "ix_persons_client_last_seen", "persons", ["client_id", "last_seen_at"]
    )
    op.create_table(
        "mention_persons",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "mention_id",
            sa.BigInteger(),
            sa.ForeignKey("mentions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "person_id",
            sa.BigInteger(),
            sa.ForeignKey("persons.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=500), nullable=True),
        sa.Column("org", sa.String(length=500), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("stance_target_id", sa.BigInteger(), nullable=True),
        sa.Column("stance_polarity", sa.SmallInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mention_id", "person_id", name="uq_mention_person"),
    )
    # Self-referencing stance target: created post-hoc with a stable name so
    # the downgrade can drop it by name (use_alter semantics).
    op.create_foreign_key(
        "fk_mention_person_stance_target",
        "mention_persons",
        "persons",
        ["stance_target_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mention_person_person", "mention_persons", ["person_id"])
    op.create_index("ix_mention_person_mention", "mention_persons", ["mention_id"])


def downgrade() -> None:
    op.drop_index("ix_mention_person_mention", table_name="mention_persons")
    op.drop_index("ix_mention_person_person", table_name="mention_persons")
    op.drop_constraint(
        "fk_mention_person_stance_target", "mention_persons", type_="foreignkey"
    )
    op.drop_table("mention_persons")
    op.drop_index("ix_persons_client_last_seen", table_name="persons")
    op.drop_table("persons")
