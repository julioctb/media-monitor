"""daily_summaries table (T11: one stored digest per client and day).

The (client_id, summary_date) unique key makes the daily build idempotent;
the extra date index serves per-day listings across clients.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-10

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# BigInteger on PostgreSQL, plain INTEGER on SQLite so the column is a
# rowid alias (mirrors 0001-0006).
DailySummaryPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "daily_summaries",
        sa.Column("id", DailySummaryPk, autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("summary_date", sa.Date(), nullable=False),
        # Structured sections + plain_text; sa.JSON renders on sqlite and PG
        # alike (no JSONB here by design, mirrors saved_searches.sources).
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "summary_date", name="uq_daily_summaries_client_date"),
    )
    op.create_index("ix_daily_summaries_date", "daily_summaries", ["summary_date"])


def downgrade() -> None:
    op.drop_index("ix_daily_summaries_date", table_name="daily_summaries")
    op.drop_table("daily_summaries")
