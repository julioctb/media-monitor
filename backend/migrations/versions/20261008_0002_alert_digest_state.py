"""alert digest state: watermark + pending marker on alert_settings

Adds the alert-engine bookkeeping columns: last_digest_at (watermark of
the last digest send) and digest_pending_since (when un-notified
mentions first appeared under a digest cadence).

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alert_settings",
        sa.Column("last_digest_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "alert_settings",
        sa.Column("digest_pending_since", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_settings", "digest_pending_since")
    op.drop_column("alert_settings", "last_digest_at")
