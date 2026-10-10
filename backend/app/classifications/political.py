"""Political classifier: does this text mainly deal with politics?

Runs on the shared LayaRuntime (the same lazy agent as sentiment — the
model loads once per process, never twice). One `choice` question,
political vs not_political; the score is the chosen option's calibrated
probability. Low-confidence choices are returned as uncertain while preserving
the chosen score. The explicit not_political option keeps the decision
two-sided instead of thresholding a single positive score.

Calibrated on backend/eval_political_gold_es.jsonl (63 real mentions,
hand-labeled; see scripts/eval_classifications.py): the default threshold is
0.50 because every higher value traded political recall for a nearly empty
uncertain band (0.55 already costs ~8 accuracy points). Raise it via
LAYA_POLITICAL_CONFIDENCE_THRESHOLD when uncertain mass is preferred over
forced labels.
"""

import logging
import os

from app.classifications.base import ClassificationResult
from app.sentiment.laya_analyzer import LayaRuntime

log = logging.getLogger("classifications.political")

CLASSIFIER_NAME = "political"
UNCERTAIN_LABEL = "uncertain"
DEFAULT_CONFIDENCE_THRESHOLD = 0.50
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
            "Is the main topic politics or government? Political means public "
            "decision-making: officials and government bodies, parties, elections, "
            "public budgets, laws, decrees, state policy, or the government "
            "relationship with an institution (autonomy, public funding, political "
            "backing or attacks). "
            "Es el tema principal politica o gobierno? Politica = decisiones "
            "publicas: funcionarios y organismos, partidos, elecciones, presupuesto, "
            "leyes, decretos, o la relacion del gobierno con la institucion "
            "(autonomia, dinero publico, respaldo o ataques politicos). Deporte, "
            "academia o cultura: no politica salvo decision o conflicto de gobierno."
        ),
        "criteria": {
            "political": (
                "Government or official action at the center, or a government vs "
                "institution conflict / accion de gobierno al centro o conflicto "
                "gobierno-institucion"
            ),
            "not_political": (
                "Sports, culture, science, academic life or internal institution "
                "management / deporte, cultura, ciencia, vida academica o gestion "
                "interna de la institucion"
            ),
        },
    }
}

# Explicit disambiguation (T12): sports/academic/cultural events are not
# political on their own — only via government decisions, conflicts, or
# political actors as the main subject (the clause closing the instructions
# above). On the 63-row gold it trades one borderline political row (the
# gov-university backing cluster) for perfect not_political recall:
# 37/63=58.73% -> 36/63=57.14%, not_political 31/34 -> 34/34. The
# misclassified-sports field report was about that side.

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
