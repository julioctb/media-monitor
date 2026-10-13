"""ingest_cursors table (T1: durable per-adapter ingest watermark).

One row per (client, adapter); the unique pair key makes the watermark
upsert idempotent. last_success_at advances only on a clean adapter pass.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-13

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ingest_cursors",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column(
            "client_id",
            sa.Integer(),
            sa.ForeignKey("clients.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("adapter_name", sa.String(length=64), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("overlap_min", sa.Integer(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_id", "adapter_name", name="uq_ingest_cursors_pair"),
    )
    op.create_index(
        "ix_ingest_cursors_client",
        "ingest_cursors",
        ["client_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingest_cursors_client", table_name="ingest_cursors")
    op.drop_table("ingest_cursors")
