"""digest_hours: comma-separated daily digest cut hours (multi-cut).

Adds ``settings.digest_hours`` (varchar, CSV of hours 0..23, default '21')
consumed by the worker scheduler and exposed through EffectiveSettings as
``digest_hours``. The legacy ``digest_hour`` column stays untouched and is
backfilled into the new one so pre-0020 rows keep their configured hour.

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-20

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "settings",
        sa.Column("digest_hours", sa.String(length=50), nullable=False, server_default="21"),
    )
    # Legacy rows keep their single configured hour as the only cut.
    op.execute("UPDATE settings SET digest_hours = CAST(digest_hour AS VARCHAR)")


def downgrade() -> None:
    op.drop_column("settings", "digest_hours")
