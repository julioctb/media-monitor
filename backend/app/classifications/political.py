"""Political classifier: does this text mainly deal with politics?

Runs on the shared LayaRuntime (the same lazy agent as sentiment — the
model loads once per process, never twice). One `choice` question,
political vs not_political; the score is the chosen option's calibrated
probability. The explicit not_political option keeps the decision
two-sided instead of thresholding a single positive score.
"""

from app.classifications.base import ClassificationResult
from app.sentiment.laya_analyzer import LayaRuntime

CLASSIFIER_NAME = "political"

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

    def __init__(self, agent=None) -> None:
        # Injectable for tests; production shares LayaRuntime's lazy agent.
        self._agent = agent

    def classify(self, text: str, lang: str = "es") -> ClassificationResult:
        agent = self._agent if self._agent is not None else LayaRuntime.agent()
        result = agent.predict(text, _POLITICAL_QUESTION)
        answer = result["answers"]["political"]
        return ClassificationResult(
            label=answer["choice"],
            score=float(answer["probabilities"][answer["choice"]]),
        )
