"""mention_classifications: unique per (mention, classifier, label)

T12 multi-label topics: one classifier (topic) emits several labels per
mention, so the (mention, classifier) pair uniqueness relaxes to the
full triple. Single-label classifiers are unaffected -- their upsert
deletes the classifier's rows before inserting, so the pair stays
unique in practice.

Note on downgrade: re-tightening to (mention, classifier) requires at
most one row per pair; re-run a single-label backfill first if
multi-label rows exist.

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-10

"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # batch_alter_table renders plain ALTERs on PostgreSQL and copes with
    # SQLite's limited ALTER, mirroring the cross-dialect model metadata.
    with op.batch_alter_table("mention_classifications") as batch:
        batch.drop_constraint("uq_mention_classifications_pair", type_="unique")
        batch.create_unique_constraint(
            "uq_mention_classifications_triple",
            ["mention_id", "classifier", "label"],
        )


def downgrade() -> None:
    with op.batch_alter_table("mention_classifications") as batch:
        batch.drop_constraint("uq_mention_classifications_triple", type_="unique")
        batch.create_unique_constraint(
            "uq_mention_classifications_pair",
            ["mention_id", "classifier"],
        )
