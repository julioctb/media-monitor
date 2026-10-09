"""initial domain schema (cross-db: sqlite + postgres)

Creates the full domain schema in a dialect-agnostic way and seeds the
default client (id=1, name='default').

Enums are declared with native_enum=False so they render as VARCHAR plus a
CHECK constraint on BOTH sqlite and postgres. Timestamps use CURRENT_TIMESTAMP,
accepted by both backends. The postgres-only sequence sync after the seed is
guarded by dialect.

Squashes the former 0001/0002/0003 chain (pre-production; no deployed
databases existed).

Revision ID: 0001
Revises:
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# VARCHAR + CHECK on every backend: portable and enforceable.
mention_source_enum = sa.Enum(
    "news_rss",
    "gdelt",
    "x_twitter",
    "facebook_page",
    name="mention_source",
    native_enum=False,
    length=32,
)
sentiment_enum = sa.Enum(
    "positive",
    "negative",
    "neutral",
    name="sentiment",
    native_enum=False,
    length=16,
)
alert_channel_enum = sa.Enum(
    "email", name="alert_channel", native_enum=False, length=16
)
alert_digest_enum = sa.Enum(
    "instant",
    "daily",
    "weekly",
    name="alert_digest",
    native_enum=False,
    length=16,
)


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
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
            server_default=sa.text("CURRENT_TIMESTAMP"),
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
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("sentiment", sentiment_enum, nullable=True),
        sa.Column("sentiment_score", sa.Float(), nullable=True),
        sa.Column("reach", sa.BigInteger(), nullable=True),
        sa.Column("raw", sa.JSON(), nullable=True),
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
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("digest_pending_since", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # Seed the default tenant.
    op.execute("INSERT INTO clients (id, name) VALUES (1, 'default')")
    # Postgres-only: keep the identity sequence in sync with the explicit
    # seed insert. SQLite rowids self-adjust.
    if op.get_bind().dialect.name == "postgresql":
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
