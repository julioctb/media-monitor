"""Classifier contract: an independent labelling axis over mention text.

A classifier names itself and maps text to one label plus a confidence
score. Results persist in mention_classifications, one row per
(mention, classifier): re-running a classifier replaces only its own
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
    """Anything with a stable registry name and a classify()."""

    name: str

    def classify(self, text: str, lang: str = "es") -> ClassificationResult:
        """Label the text; ``lang`` is a BCP-47 hint (unused so far)."""
        ...
