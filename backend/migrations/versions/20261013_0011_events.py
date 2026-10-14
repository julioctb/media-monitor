"""events table + mentions.event_id (Phase 2 T1: canonical event clusters).

One row per canonical fact; mentions point at their event and are
nulled out when the event disappears.

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=1000), nullable=False),
        sa.Column("title_tokens", sa.String(length=500), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_events_client_first_seen", "events", ["client_id", "first_seen_at"]
    )
    op.add_column(
        "mentions",
        sa.Column("event_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_mentions_event_id_events",
        "mentions",
        "events",
        ["event_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_mentions_event_id", "mentions", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_mentions_event_id", table_name="mentions")
    op.drop_constraint("fk_mentions_event_id_events", "mentions", type_="foreignkey")
    op.drop_column("mentions", "event_id")
    op.drop_index("ix_events_client_first_seen", table_name="events")
    op.drop_table("events")
