"""MentionClassification: one label from one classifier for a mention.

Multi-label by design: a classifier may emit several labels for one
mention -- one row per (mention, classifier, label) under a triple
unique -- and classifiers are independent axes, so a political note can
still be sentiment-positive while carrying two topics. The classifier
catalog lives in code (app.classifications registry), NOT in a CHECK
constraint: adding a classifier is a deploy, never a migration.
"""

from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IntPk


class MentionClassification(IntPk, Base):
    __tablename__ = "mention_classifications"
    __table_args__ = (
        # One row per (mention, classifier, label): multi-label classifiers
        # store several labels for the same mention/classifier pair.
        UniqueConstraint(
            "mention_id",
            "classifier",
            "label",
            name="uq_mention_classifications_triple",
        ),
        # Hot path: stats breakdown groups by label inside a classifier and
        # the feed filter probes (classifier, label) existence.
        Index("ix_mention_classifications_classifier_label", "classifier", "label"),
    )

    mention_id: Mapped[int] = mapped_column(
        ForeignKey("mentions.id", ondelete="CASCADE"), nullable=False
    )
    classifier: Mapped[str] = mapped_column(String(32), nullable=False)
    label: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    mention = relationship("Mention", back_populates="classifications")

    def __repr__(self) -> str:
        return (
            f"<MentionClassification mention_id={self.mention_id} "
            f"classifier={self.classifier} label={self.label}>"
        )
