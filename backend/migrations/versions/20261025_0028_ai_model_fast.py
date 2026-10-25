"""settings.ai_model_fast: model for the fast/structured LLM tier (T2a).

Falls back to ai_model when unset; nullable so no server default is needed.

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-25
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("ai_model_fast", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "ai_model_fast")
