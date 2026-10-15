"""Scraper ingestion: mentions.source domain + settings.scrapers column.

Widens the ck_mentions_source CHECK to the new ``scraper`` value and adds
the per-client ``scrapers`` JSON list (keys of
app.ingest.scrapers.SCRAPER_REGISTRY). source is VARCHAR + CHECK on every
backend (0001 uses native_enum=False), so the batched rebuild covers
SQLite and PostgreSQL alike; the column default seeds existing rows.

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-15

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with app.models.base.MentionSource / app.models.mention.
MENTION_SOURCES = (
    "news_rss",
    "gdelt",
    "x_twitter",
    "facebook_page",
    "rss_custom",
    "scraper",
)


def _source_check_condition() -> str:
    values = ", ".join(f"'{value}'" for value in MENTION_SOURCES)
    return f"source IN ({values})"


def upgrade() -> None:
    # settings.scrapers: NOT NULL needs a server default for existing rows;
    # the ORM default (list) covers new inserts.
    op.add_column(
        "settings",
        sa.Column("scrapers", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    # source is VARCHAR + CHECK on every backend (0001 uses native_enum=False);
    # only the CHECK domain needs widening.
    with op.batch_alter_table("mentions") as batch_op:
        batch_op.drop_constraint("ck_mentions_source", type_="check")
        batch_op.create_check_constraint(
            "ck_mentions_source", sa.text(_source_check_condition())
        )


def downgrade() -> None:
    with op.batch_alter_table("mentions") as batch_op:
        batch_op.drop_constraint("ck_mentions_source", type_="check")
        batch_op.create_check_constraint(
            "ck_mentions_source",
            sa.text(
                "source IN ('news_rss', 'gdelt', 'x_twitter', 'facebook_page', 'rss_custom')"
            ),
        )
    op.drop_column("settings", "scrapers")
