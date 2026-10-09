"""Classifier registry: name -> factory, the single source of truth.

Adding a classifier = write the module, register the factory here. The
mention_classifications.classifier column is a plain string keyed by
these names, so registration never touches the schema.

``build_classifiers`` instances validate their ``name`` against the key
they were registered under; a mismatch is a bug worth failing on.
"""

from typing import Callable

from app.classifications.base import Classifier
from app.classifications.political import PoliticalClassifier

CLASSIFIER_FACTORIES: dict[str, Callable[[], Classifier]] = {
    PoliticalClassifier.name: PoliticalClassifier,
}


def classifier_names() -> list[str]:
    """Registered classifier names, registry order."""
    return list(CLASSIFIER_FACTORIES)


def build_classifiers(names: list[str] | None = None) -> list[Classifier]:
    """Instantiate the whole registry, or the named subset.

    Raises KeyError for unknown names (typo-safe CLI/scripts).
    """
    if names is None:
        selected = dict(CLASSIFIER_FACTORIES)
    else:
        unknown = [name for name in names if name not in CLASSIFIER_FACTORIES]
        if unknown:
            raise KeyError(f"unknown classifiers: {unknown}")
        selected = {name: CLASSIFIER_FACTORIES[name] for name in names}
    instances = [factory() for key, factory in selected.items()]
    for key, instance in zip(selected, instances):
        if instance.name != key:
            raise ValueError(
                f"classifier factory for {key!r} built instance named {instance.name!r}"
            )
    return instances
