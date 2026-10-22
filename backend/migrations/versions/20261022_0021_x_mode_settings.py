"""x_mode + x_api_key: settings-driven X source (free index / paid API).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-22
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # x_mode enum is enforced at the validation layer (queries), not by a
    # DB CHECK, so the migration stays dialect-agnostic (sqlite-safe).
    op.add_column(
        "settings",
        sa.Column("x_mode", sa.String(length=8), nullable=False, server_default="free"),
    )
    op.add_column("settings", sa.Column("x_api_key", sa.String(length=500), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "x_api_key")
    op.drop_column("settings", "x_mode")
