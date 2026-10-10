"""Topic classifier: the ONE subject the text is mostly about.

Single-label by design: ONE ``predict`` call resolves a six-way ``choice``
-- sports, academic, culture, health, economy, other -- and the winning
option becomes the label, carrying its probability; the same shape as the
political classifier. The dominant theme wins: a derby cronica is sports
even when it also mentions ticket prices, and a mention never carries two
topics. Runs on the shared LayaRuntime (the same lazy agent as sentiment
and political -- one model load per process, never twice).

Why `choice` and not `noul`: on this checkpoint the choice head
separates far cleaner (10-probe harness: 9/10 intended hits at 0.5 with
few false positives, vs a mushy 0.06-0.46 band from `noul`) -- the same
head the sentiment and political classifiers already trust.

``other`` is a real outcome, not a stored label: when the model picks it
(no area dominates, or purely institutional/corporate copy) the
classifier returns no result, so the pipeline stores no row -- an absent
topic means the mention has no theme. A re-run clears the stale row
through the plural upsert's delete-plus-insert.
"""

from app.classifications.base import ClassificationResult
from app.sentiment.laya_analyzer import LayaRuntime

CLASSIFIER_NAME = "topic"
TOPIC_KEY = "topic"
OTHER_LABEL = "other"

# One six-way choice: the dominant-theme rule lives in the instructions,
# each option carries a short bilingual criterion. Mirrors the political
# question's shape (one entry, `choice` type).
_TOPIC_QUESTION = {
    TOPIC_KEY: {
        "type": "choice",
        "instructions": (
            "Which ONE topic dominates the piece? Pick the single subject it "
            "is mostly about -- one only, not every topic it touches. If no "
            "area clearly dominates, or the piece is purely institutional or "
            "corporate copy with no subject area, answer other. "
            "Cual es el UNICO tema dominante de la nota? Elegir un solo tema, "
            "el del que principalmente habla, no todos los que menciona. Si "
            "ninguno domina, o la nota es puramente institucional corporativa "
            "sin tema: other."
        ),
        "criteria": {
            "sports": (
                "Sports at the center: games, results, teams, players, "
                "tournaments / deporte: partidos, resultados, equipos, jugadores"
            ),
            "academic": (
                "Academic life at the center: studies, research, students, "
                "exams, campus / vida academica: estudios, investigacion, alumnos"
            ),
            "culture": (
                "Culture or entertainment at the center: art, music, film, "
                "shows, books / cultura: arte, musica, cine, espectaculos, libros"
            ),
            "health": (
                "Health at the center: medicine, hospitals, diseases, "
                "vaccines / salud: medicina, hospitales, enfermedades, vacunas"
            ),
            "economy": (
                "Economy at the center: markets, companies, prices, jobs, "
                "trade / economia: mercados, empresas, precios, empleo, comercio"
            ),
            OTHER_LABEL: (
                "No area dominates, or purely institutional/corporate notice / "
                "sin area dominante o nota institucional corporativa"
            ),
        },
    }
}


class TopicClassifier:
    """Dominant topic via one six-way choice, political-classifier style.

    The chosen option's probability rides along as the score. ``other``
    maps to an empty result: nothing is persisted, so a mention without a
    dominant theme carries no topic row at all.
    """

    name = CLASSIFIER_NAME

    def __init__(self, agent=None) -> None:
        # Injectable for tests/scripts; production shares LayaRuntime's lazy agent.
        self._agent = agent

    def classify(
        self, text: str, lang: str = "es"
    ) -> ClassificationResult | list[ClassificationResult]:
        agent = self._agent if self._agent is not None else LayaRuntime.agent()
        result = agent.predict(text, _TOPIC_QUESTION)
        answer = result["answers"][TOPIC_KEY]
        choice = answer["choice"]
        score = float(answer["probabilities"][choice])
        if choice == OTHER_LABEL:
            # No dominant theme: store nothing (topic ausente = sin tema).
            return []
        return ClassificationResult(label=choice, score=score)
