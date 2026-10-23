"""daily_summary_revisions: append-only narrative history per digest.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0023"
down_revision: Union[str, None] = "0022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "daily_summary_revisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_date", sa.Date(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "client_id", "summary_date", "seq", name="uq_summary_revisions_client_day_seq"
        ),
    )
    op.create_index(
        "ix_summary_revisions_day",
        "daily_summary_revisions",
        ["client_id", "summary_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_summary_revisions_day", table_name="daily_summary_revisions")
    op.drop_table("daily_summary_revisions")
