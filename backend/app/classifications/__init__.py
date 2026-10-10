"""Classification package: registry-backed mention classifiers."""

from app.classifications.base import ClassificationResult, Classifier
from app.classifications.political import PoliticalClassifier
from app.classifications.registry import (
    CLASSIFIER_FACTORIES,
    build_classifiers,
    classifier_names,
)
from app.classifications.topics import TopicClassifier

__all__ = [
    "CLASSIFIER_FACTORIES",
    "ClassificationResult",
    "Classifier",
    "PoliticalClassifier",
    "TopicClassifier",
    "build_classifiers",
    "classifier_names",
]
