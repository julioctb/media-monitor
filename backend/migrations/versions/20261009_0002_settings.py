"""settings table + mentions.source CHECK including rss_custom

Adds the per-client settings row (lazy-created on first read, no seed)
and enforces the mention source domain with a CHECK constraint that
includes the new ``rss_custom`` value. The constraint is created through
batch_alter_table so SQLite rebuilds the table (its ALTER is limited)
while PostgreSQL emits a plain ALTER TABLE ... ADD CONSTRAINT.

Note: 0001 rendered ``mentions.source`` as plain VARCHAR on every
backend (SQLAlchemy >= 1.4 no longer emits CHECK constraints for
non-native enums by default), so there is nothing to drop here — this
migration is the constraint's birth, now covering all five values.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with app.models.base.MentionSource / app.models.settings.
MENTION_SOURCES = ("news_rss", "gdelt", "x_twitter", "facebook_page", "rss_custom")
# BigInteger on PostgreSQL (serial via PK), plain INTEGER on SQLite so the
# column is a rowid alias and inserts without id autoincrement.
SettingsPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def _source_check_condition() -> str:
    values = ", ".join(f"'{value}'" for value in MENTION_SOURCES)
    return f"source IN ({values})"


def upgrade() -> None:
    op.create_table(
        "settings",
        sa.Column("id", SettingsPk, autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_name", sa.String(length=200), nullable=False, server_default=""),
        sa.Column(
            "timezone",
            sa.String(length=64),
            nullable=False,
            server_default="America/Mexico_City",
        ),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="365"),
        sa.Column("gdelt_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("facebook_pages", sa.JSON(), nullable=False),
        sa.Column("rss_feeds", sa.JSON(), nullable=False),
        sa.Column(
            "ai_provider", sa.String(length=16), nullable=False, server_default="local"
        ),
        sa.Column("ai_api_key", sa.String(length=500), nullable=True),
        sa.Column(
            "ai_base_url",
            sa.String(length=500),
            nullable=True,
            server_default="https://api.openai.com/v1",
        ),
        sa.Column("ai_model", sa.String(length=100), nullable=True),
        sa.Column(
            "ai_fallback_local", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", name="uq_settings_client"),
        sa.CheckConstraint(
            "ai_provider IN ('local', 'openai')", name="ck_settings_ai_provider"
        ),
    )

    with op.batch_alter_table("mentions") as batch_op:
        batch_op.create_check_constraint(
            "ck_mentions_source", sa.text(_source_check_condition())
        )


def downgrade() -> None:
    with op.batch_alter_table("mentions") as batch_op:
        batch_op.drop_constraint("ck_mentions_source", type_="check")
    op.drop_table("settings")
