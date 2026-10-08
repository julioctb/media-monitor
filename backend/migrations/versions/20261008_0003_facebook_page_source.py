"""mention_source enum: add facebook_page

Adds the facebook_page value to the mention_source enum for the Facebook
Pages adapter (T8). No table changes: existing rows keep their values.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL 12+ allows ADD VALUE inside a transaction; the value is
    # not used later in this migration, so the same-transaction caveat
    # does not apply.
    op.execute("ALTER TYPE mention_source ADD VALUE IF NOT EXISTS 'facebook_page'")


def downgrade() -> None:
    # PostgreSQL has no ALTER TYPE ... DROP VALUE on any supported
    # release; dropping the label would require rebuilding the type and
    # rewriting mentions.source. An unused enum label is harmless, so the
    # downgrade is a deliberate no-op.
    pass
