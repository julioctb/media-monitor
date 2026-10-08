"""initial domain model: clients, keywords, mentions, alert_settings

Creates the full domain schema with native Postgres enums and indexes, and
seeds the default client (id=1, name='default').

Revision ID: 0001
Revises:
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

mention_source_enum = postgresql.ENUM(
    "news_rss", "gdelt", "x_twitter", name="mention_source", create_type=False
)
sentiment_enum = postgresql.ENUM(
    "positive", "negative", "neutral", name="sentiment", create_type=False
)
alert_channel_enum = postgresql.ENUM(
    "email", name="alert_channel", create_type=False
)
alert_digest_enum = postgresql.ENUM(
    "instant", "daily", "weekly", name="alert_digest", create_type=False
)


def upgrade() -> None:
    # Enum types must exist before the tables reference them.
    for enum_ddl in (
        "CREATE TYPE mention_source AS ENUM ('news_rss', 'gdelt', 'x_twitter')",
        "CREATE TYPE sentiment AS ENUM ('positive', 'negative', 'neutral')",
        "CREATE TYPE alert_channel AS ENUM ('email')",
        "CREATE TYPE alert_digest AS ENUM ('instant', 'daily', 'weekly')",
    ):
        op.execute(enum_ddl)

    op.create_table(
        "clients",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_clients_name"),
    )

    op.create_table(
        "keywords",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "text", name="uq_keywords_client_text"),
    )

    op.create_table(
        "mentions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "keyword_id",
            sa.BigInteger(),
            sa.ForeignKey("keywords.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", mention_source_enum, nullable=False),
        sa.Column("external_id", sa.String(length=500), nullable=True),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("url_hash", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=1000), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("author", sa.String(length=500), nullable=True),
        sa.Column("lang", sa.String(length=8), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("sentiment", sentiment_enum, nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("reach", sa.BigInteger(), nullable=True),
        sa.Column("raw", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url_hash", name="uq_mentions_url_hash"),
    )
    op.create_index(
        "ix_mentions_client_published",
        "mentions",
        ["client_id", "published_at"],
    )
    op.create_index("ix_mentions_client_source", "mentions", ["client_id", "source"])
    op.create_index("ix_mentions_url_hash", "mentions", ["url_hash"])

    op.create_table(
        "alert_settings",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.BigInteger(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("channel", alert_channel_enum, nullable=False),
        sa.Column("digest", alert_digest_enum, nullable=False),
        sa.Column("recipient_email", sa.String(length=320), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed the default tenant.
    op.execute("INSERT INTO clients (id, name) VALUES (1, 'default')")
    # Keep the id sequence in sync with the explicit seed insert.
    op.execute(
        "SELECT setval(pg_get_serial_sequence('clients', 'id'), 1, true)"
    )


def downgrade() -> None:
    op.drop_table("alert_settings")
    op.drop_index("ix_mentions_url_hash", table_name="mentions")
    op.drop_index("ix_mentions_client_source", table_name="mentions")
    op.drop_index("ix_mentions_client_published", table_name="mentions")
    op.drop_table("mentions")
    op.drop_table("keywords")
    op.drop_table("clients")
    for type_name in ("alert_digest", "alert_channel", "sentiment", "mention_source"):
        op.execute(f"DROP TYPE IF EXISTS {type_name}")
