"""alert_settings sentiment-shift columns (T4).

Three additive columns for the sentiment-shift rule: enable flag, net
swing threshold (percentage points) and the dedupe watermark. Backfilled
via server defaults so existing rows keep alerting behavior unchanged.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "alert_settings",
        sa.Column("sentiment_shift_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "alert_settings",
        sa.Column("sentiment_shift_threshold", sa.Float(), nullable=False, server_default="10"),
    )
    op.add_column(
        "alert_settings",
        sa.Column("sentiment_shift_last_sent", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_settings", "sentiment_shift_last_sent")
    op.drop_column("alert_settings", "sentiment_shift_threshold")
    op.drop_column("alert_settings", "sentiment_shift_enabled")
