"""settings.watchlist: person_ids under vigilance (F7), JSON array.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0027"
down_revision: Union[str, None] = "0026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("watchlist", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("settings", "watchlist")
