"""digest_hour: local hour for the daily digest build (digest v2).

Adds the per-client ``digest_hour`` integer (0..23, default 21) consumed by
the worker scheduler and exposed through EffectiveSettings.

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-18

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0018"
down_revision: Union[str, None] = "0017"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("digest_hour", sa.Integer(), nullable=False, server_default="21"),
    )


def downgrade() -> None:
    op.drop_column("settings", "digest_hour")
