"""Persist the reviewer guided-envelope mode (json_schema/json_object/plain).

Revision ID: 0033
Revises: 0032
"""

import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "digest_reviewer_guided_mode",
            sa.String(16),
            nullable=False,
            server_default="json_schema",
        ),
    )


def downgrade() -> None:
    op.drop_column("settings", "digest_reviewer_guided_mode")
