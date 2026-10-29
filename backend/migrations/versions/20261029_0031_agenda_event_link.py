"""agenda_event_link: vinculo agenda_items.event_id (feed reactivo al filtro).

Revision ID: 0031
Revises: 0030
Create Date: 2026-10-29
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "agenda_items",
        sa.Column(
            "event_id",
            sa.Integer(),
            sa.ForeignKey("events.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_agenda_items_event_id", "agenda_items", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_agenda_items_event_id", table_name="agenda_items")
    op.drop_column("agenda_items", "event_id")
