"""agenda_items: client agenda (feature agenda-page).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agenda_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False, server_default="activity"),
        sa.Column("event_date", sa.Date(), nullable=True),
        sa.Column("date_label", sa.String(length=64), nullable=True),
        sa.Column("time_label", sa.String(length=16), nullable=True),
        sa.Column("location", sa.String(length=200), nullable=True),
        sa.Column("source", sa.String(length=200), nullable=True),
        sa.Column("url", sa.String(length=500), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_agenda_items_client_event_date",
        "agenda_items",
        ["client_id", "event_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_agenda_items_client_event_date", table_name="agenda_items")
    op.drop_table("agenda_items")
