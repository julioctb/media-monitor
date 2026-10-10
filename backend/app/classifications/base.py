"""Classifier contract: an independent labelling axis over mention text.

A classifier names itself and maps text to one label plus a confidence
score -- or, for multi-label classifiers, to a list of such results.
Results persist in mention_classifications, one row per
(mention, classifier, label): re-running a classifier replaces all of its
rows, and sentiment stays a separate axis (a political note can be
positive).
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ClassificationResult:
    """Chosen label with the classifier's confidence in it (0..1)."""

    label: str
    score: float


@runtime_checkable
class Classifier(Protocol):
    """Anything with a stable registry name and a classify().

    classify() returns one result, or a list of them -- multi-label
    classifiers emit every winning label; app.classifications.topics
    returns an empty list when no dominant theme wins (``other``), which
    persists as no rows.
    """

    name: str

    def classify(
        self, text: str, lang: str = "es"
    ) -> ClassificationResult | list[ClassificationResult]:
        """Label the text; ``lang`` is a BCP-47 hint (unused so far)."""
        ...


def classification_results(
    outcome: ClassificationResult | list[ClassificationResult],
) -> list[ClassificationResult]:
    """Normalize a classifier's outcome to a list of results.

    Single-label classifiers return one result; multi-label ones return
    the yes-labeled subset. Callers (pipeline, backfill) persist through
    the plural upsert either way.
    """
    return outcome if isinstance(outcome, list) else [outcome]
