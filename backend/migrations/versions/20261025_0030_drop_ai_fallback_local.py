"""Drop legacy settings.ai_fallback_local (dead since the laya removal).

Revision ID: 0030
Revises: 0029
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("settings", "ai_fallback_local")


def downgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "ai_fallback_local",
            sa.Boolean(),
            nullable=False,
            server_default="1",
        ),
    )
