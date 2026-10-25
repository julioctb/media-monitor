"""event_merges: audit of event-identity arbitrations (T2b).

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "event_merges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_from", sa.Integer(), nullable=False),
        sa.Column("event_to", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("verdict", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=300), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_event_merges_client_created",
        "event_merges",
        ["client_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_event_merges_client_created", table_name="event_merges")
    op.drop_table("event_merges")
