"""Article-fetch knob: settings.fetch_max_per_cycle (F2c-article-fetch).

Caps the per-cycle article content fetches the same way 0012 caps LLM
enrichments; the overflow is backfill work (scripts/backfill_content.py).

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-14

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("fetch_max_per_cycle", sa.Integer(), nullable=False, server_default="20"),
    )


def downgrade() -> None:
    op.drop_column("settings", "fetch_max_per_cycle")
