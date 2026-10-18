"""digest_focus_person_id: the digest RECTORA section focus person.

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-18

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("settings", sa.Column("digest_focus_person_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("settings", "digest_focus_person_id")
