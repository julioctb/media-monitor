"""Persist independent per-tenant report reviewer settings.

Revision ID: 0032
Revises: 0031
"""

import sqlalchemy as sa
from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column(
            "digest_reviewer_provider",
            sa.String(16),
            nullable=False,
            server_default="inherit",
        ),
    )
    op.add_column("settings", sa.Column("digest_reviewer_base_url", sa.String(500)))
    op.add_column("settings", sa.Column("digest_reviewer_model", sa.String(100)))
    op.add_column("settings", sa.Column("digest_reviewer_api_key", sa.String(500)))
    op.add_column("settings", sa.Column("digest_reviewer_revision", sa.String(36)))


def downgrade() -> None:
    for column in (
        "digest_reviewer_revision",
        "digest_reviewer_api_key",
        "digest_reviewer_model",
        "digest_reviewer_base_url",
        "digest_reviewer_provider",
    ):
        op.drop_column("settings", column)
