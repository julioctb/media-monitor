"""Mentions.raw_enrichment: full EnrichmentResult dump for F3 read-back.

Persists the complete enrichment payload (persons with stance, topics,
sentiment) at enrichment time so downstream features read it without
re-running the LLM. Backfilled for pre-existing rows via
scripts/backfill_enrichment --force.

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mentions", sa.Column("raw_enrichment", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("mentions", "raw_enrichment")
