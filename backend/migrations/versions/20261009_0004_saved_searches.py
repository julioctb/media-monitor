"""saved_searches table (T1: persisted client queries).

A saved search is a stored filter bundle (query text, source subset,
classifier/label probe) resolved through queries._mention_filters; the
unique (client_id, name) key keeps the list UI predictable.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# BigInteger on PostgreSQL, plain INTEGER on SQLite so the column is a
# rowid alias (mirrors 0001-0003).
SavedSearchPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "saved_searches",
        sa.Column("id", SavedSearchPk, autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("query", sa.String(length=500), nullable=False),
        # sa.JSON renders on sqlite and PG alike (no JSONB here by design).
        sa.Column("sources", sa.JSON(), nullable=False),
        sa.Column("classifier", sa.String(length=32), nullable=True),
        sa.Column("label", sa.String(length=32), nullable=True),
        sa.Column("range_days", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "name", name="uq_saved_searches_client_name"),
    )
    op.create_index(
        "ix_saved_searches_client_active",
        "saved_searches",
        ["client_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_searches_client_active", table_name="saved_searches")
    op.drop_table("saved_searches")
