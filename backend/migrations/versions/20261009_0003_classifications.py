"""mention_classifications table (T10: multi-label classifiers)

One row per (mention, classifier): the label catalog lives in the
app.classifications registry, so new classifiers/labels need no CHECK,
enum or migration here. The (classifier, label) index backs the stats
breakdown and the mention-feed existence filter.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# BigInteger on PostgreSQL, plain INTEGER on SQLite so the column is a
# rowid alias and inserts without id autoincrement (mirrors 0001/0002).
ClassificationPk = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "mention_classifications",
        sa.Column("id", ClassificationPk, autoincrement=True, nullable=False),
        sa.Column(
            "mention_id",
            sa.BigInteger(),
            sa.ForeignKey("mentions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("classifier", sa.String(length=32), nullable=False),
        sa.Column("label", sa.String(length=32), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("mention_id", "classifier", name="uq_mention_classifications_pair"),
    )
    op.create_index(
        "ix_mention_classifications_classifier_label",
        "mention_classifications",
        ["classifier", "label"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_mention_classifications_classifier_label",
        table_name="mention_classifications",
    )
    op.drop_table("mention_classifications")
