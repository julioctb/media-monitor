"""field_operators invite flow: single-use token + acceptance stamp.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-23
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0026"
down_revision: Union[str, None] = "0025"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("field_operators", sa.Column("invite_token", sa.String(length=32), nullable=True))
    op.add_column("field_operators", sa.Column("invited_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("field_operators", sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "uq_field_operators_invite_token", "field_operators", ["invite_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_field_operators_invite_token", table_name="field_operators")
    op.drop_column("field_operators", "accepted_at")
    op.drop_column("field_operators", "invited_at")
    op.drop_column("field_operators", "invite_token")
