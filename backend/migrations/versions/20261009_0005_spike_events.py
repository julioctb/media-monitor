"""spike_events table (T2: saved-search spike detection).

One row per anomalous hourly bucket per saved search; the unique
(saved_search_id, window_start) key makes repeated scans idempotent.
Summary columns are written by the T3 summary pass.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SpikeEventPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "spike_events",
        sa.Column("id", SpikeEventPk, autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "saved_search_id",
            sa.Integer(),
            sa.ForeignKey("saved_searches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("baseline_mean", sa.Float(), nullable=False),
        sa.Column("baseline_stddev", sa.Float(), nullable=False),
        sa.Column("zscore", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("summary_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "saved_search_id", "window_start", name="uq_spike_events_search_window"
        ),
    )
    op.create_index(
        "ix_spike_events_client_window",
        "spike_events",
        ["client_id", "window_start"],
    )


def downgrade() -> None:
    op.drop_index("ix_spike_events_client_window", table_name="spike_events")
    op.drop_table("spike_events")
