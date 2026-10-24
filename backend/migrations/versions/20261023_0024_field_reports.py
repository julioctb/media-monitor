"""field_reports + field_operators: the human (Telegram) channel of the feed.

Also registers the ``field_report`` mention source (PG enum + CHECK).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SOURCES_WITH_FIELD = (
    "'news_rss', 'gdelt', 'x_twitter', 'facebook_page', "
    "'rss_custom', 'scraper', 'field_report'"
)


def upgrade() -> None:
    # mentions.source is VARCHAR + CHECK on production (no native enum type);
    # widen the check to include the new source.
    op.drop_constraint("ck_mentions_source", "mentions", type_="check")
    op.create_check_constraint(
        "ck_mentions_source",
        "mentions",
        f"source IN ({_SOURCES_WITH_FIELD})",
    )

    op.create_table(
        "field_operators",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "uq_field_operators_client_tg",
        "field_operators",
        ["client_id", "telegram_user_id"],
        unique=True,
    )

    op.create_table(
        "field_reports",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "operator_id",
            sa.Integer(),
            sa.ForeignKey("field_operators.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("place", sa.String(length=500), nullable=True),
        sa.Column("happened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("intake", sa.JSON(), nullable=True),
        sa.Column("title", sa.String(length=1000), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("review_note", sa.Text(), nullable=True),
        sa.Column(
            "mention_id",
            sa.Integer(),
            sa.ForeignKey("mentions.id", ondelete="SET NULL"),
            nullable=True,
            unique=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('draft', 'review', 'published', 'rejected')",
            name="ck_field_reports_status",
        ),
    )
    op.create_index(
        "ix_field_reports_client_status", "field_reports", ["client_id", "status"]
    )
    op.create_index(
        "ix_field_reports_client_created", "field_reports", ["client_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_field_reports_client_created", table_name="field_reports")
    op.drop_index("ix_field_reports_client_status", table_name="field_reports")
    op.drop_table("field_reports")
    op.drop_index("uq_field_operators_client_tg", table_name="field_operators")
    op.drop_table("field_operators")
    op.drop_constraint("ck_mentions_source", "mentions", type_="check")
    op.create_check_constraint(
        "ck_mentions_source",
        "mentions",
        "source IN ('news_rss', 'gdelt', 'x_twitter', 'facebook_page', "
        "'rss_custom', 'scraper')",
    )
    # The PG enum value stays: ALTER TYPE ... DROP VALUE does not exist.
