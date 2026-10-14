"""Enrichment columns: mentions/events summary + enrich cap (F2c).

mentions.summary and events.summary back the LLM enrichment pipeline
(NULL = not yet enriched / backfillable); settings.enrich_max_per_cycle
caps the per-cycle LLM spend, the overflow being backfill work.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mentions", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column(
        "settings",
        sa.Column(
            "enrich_max_per_cycle", sa.Integer(), nullable=False, server_default="50"
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "enrich_max_per_cycle")
    op.drop_column("events", "summary")
    op.drop_column("mentions", "summary")
