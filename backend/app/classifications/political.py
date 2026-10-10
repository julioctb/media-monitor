"""Political classifier: does this text mainly deal with politics?

Runs on the shared LayaRuntime (the same lazy agent as sentiment — the
model loads once per process, never twice). One `choice` question,
political vs not_political; the score is the chosen option's calibrated
probability. Low-confidence choices are returned as uncertain while preserving
the chosen score. The explicit not_political option keeps the decision
two-sided instead of thresholding a single positive score.
"""

import logging
import os

from app.classifications.base import ClassificationResult
from app.sentiment.laya_analyzer import LayaRuntime

log = logging.getLogger("classifications.political")

CLASSIFIER_NAME = "political"
UNCERTAIN_LABEL = "uncertain"
DEFAULT_CONFIDENCE_THRESHOLD = 0.70
THRESHOLD_ENV = "LAYA_POLITICAL_CONFIDENCE_THRESHOLD"


def default_confidence_threshold() -> float:
    """Runtime threshold for forced labels; invalid env values fall back safely."""
    raw = os.getenv(THRESHOLD_ENV, "").strip()
    if not raw:
        return DEFAULT_CONFIDENCE_THRESHOLD
    try:
        value = float(raw)
    except ValueError:
        log.warning(
            "invalid %s=%r; using %.2f",
            THRESHOLD_ENV,
            raw,
            DEFAULT_CONFIDENCE_THRESHOLD,
        )
        return DEFAULT_CONFIDENCE_THRESHOLD
    if 0 <= value <= 1:
        return value
    log.warning(
        "%s must be between 0 and 1; using %.2f",
        THRESHOLD_ENV,
        DEFAULT_CONFIDENCE_THRESHOLD,
    )
    return DEFAULT_CONFIDENCE_THRESHOLD

_POLITICAL_QUESTION = {
    "political": {
        "type": "choice",
        "instructions": (
            "Does this text mainly deal with politics? Political means government, "
            "political parties, elections, public policy, legislation, public officials "
            "or political conflict, or prominent political actors/institutions. "
            "A university or company in a non-political context is NOT political, "
            "even when it cites authorities. "
            "Trata principalmente de política? Política = gobierno, partidos, elecciones, "
            "políticas públicas, legislación, funcionarios o conflicto político, o "
            "protagonismo de actores o instituciones políticas. Una universidad o empresa "
            "en contexto apolítico NO es política, aunque cite autoridades."
        ),
        "criteria": {
            "political": (
                "Core topic is government, parties, elections, public policy, "
                "legislation, officials or political conflict / el núcleo es gobierno, "
                "partidos, elecciones, políticas públicas, legislación, funcionarios "
                "o conflicto político"
            ),
            "not_political": (
                "Business, culture, sports, science or any topic without a political "
                "core / negocios, cultura, deporte, ciencia u otro tema sin núcleo "
                "político"
            ),
        },
    }
}


class PoliticalClassifier:
    """political vs not_political via the shared Laya runtime."""

    name = CLASSIFIER_NAME

    def __init__(self, agent=None, confidence_threshold: float | None = None) -> None:
        # Injectable for tests/scripts; production shares LayaRuntime's lazy agent.
        self._agent = agent
        self.confidence_threshold = (
            default_confidence_threshold()
            if confidence_threshold is None
            else confidence_threshold
        )

    def classify(self, text: str, lang: str = "es") -> ClassificationResult:
        agent = self._agent if self._agent is not None else LayaRuntime.agent()
        result = agent.predict(text, _POLITICAL_QUESTION)
        answer = result["answers"]["political"]
        choice = answer["choice"]
        score = float(answer["probabilities"][choice])
        label = choice if score >= self.confidence_threshold else UNCERTAIN_LABEL
        return ClassificationResult(label=label, score=score)
