"""ingest_runs table (T3: per-adapter per-cycle ledger).

One row per adapter pass; status ok|error with the exception text on
failure. Backs GET /clients/{id}/ingest/runs (gap visibility).

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("adapter_name", sa.String(length=64), nullable=False),
        sa.Column("cycle_started", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("items_seen", sa.Integer(), nullable=False),
        sa.Column("inserted", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('ok', 'error')", name="ck_ingest_runs_status"),
    )
    op.create_index(
        "ix_ingest_runs_client_started",
        "ingest_runs",
        ["client_id", "cycle_started"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingest_runs_client_started", table_name="ingest_runs")
    op.drop_table("ingest_runs")
