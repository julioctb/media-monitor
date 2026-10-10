"""Topic classifier: which subject areas does the text touch?

Multi-label by design: ONE ``predict`` call evaluates five binary
yes/no (`choice`) questions in a single parallel forward pass -- sports,
academic, culture, health, economy -- and every yes above the threshold
becomes a label carrying its yes-probability. A derby cronica is sports;
a festival with ticket prices is culture and economy at once. Runs on
the shared LayaRuntime (the same lazy agent as sentiment and political
-- one model load per process, never twice).

Why `choice` and not `noul`: on this checkpoint the yes/no choice head
separates far cleaner (10-probe harness: 9/10 intended hits at 0.5 with
few false positives, vs a mushy 0.06-0.46 band from `noul`) -- the same
head the sentiment and political classifiers already trust.

Labels are not mutually exclusive: a mention can be academic and
culture, or health and economy. An empty result is valid: text about
none of the five areas simply carries no topic rows.
"""

from app.classifications.base import ClassificationResult
from app.sentiment.laya_analyzer import LayaRuntime

CLASSIFIER_NAME = "topic"
DEFAULT_YES_THRESHOLD = 0.5

_NO_OPTION = "another topic or none of those / otro tema"

# One binary yes/no question per category, all evaluated together. The
# domain detail lives in the yes criterion; the question stays preset-short.
_TOPIC_QUESTIONS = {
    "sports": {
        "type": "choice",
        "instructions": "Does the text center on sports?",
        "criteria": {
            "yes": (
                "sports: results, teams, tournaments, leagues, athletes, "
                "matches / resultados, equipos, torneos, ligas, atletas, partidos"
            ),
            "no": _NO_OPTION,
        },
    },
    "academic": {
        "type": "choice",
        "instructions": "Does the text center on academic life?",
        "criteria": {
            "yes": (
                "academic life: research, congresses, papers, students, exams, "
                "scholarships / investigacion, congresos, publicaciones, "
                "alumnos, examenes, becas academicas"
            ),
            "no": _NO_OPTION,
        },
    },
    "culture": {
        "type": "choice",
        "instructions": "Does the text center on culture?",
        "criteria": {
            "yes": (
                "culture: art, music, theater, literature, cultural events / "
                "arte, musica, teatro, literatura, eventos culturales"
            ),
            "no": _NO_OPTION,
        },
    },
    "health": {
        "type": "choice",
        "instructions": "Does the text center on health?",
        "criteria": {
            "yes": (
                "health: medicine, hospitals, diseases, vaccination, health "
                "campaigns / medicina, hospitales, enfermedades, vacunacion, "
                "campanas sanitarias"
            ),
            "no": _NO_OPTION,
        },
    },
    "economy": {
        "type": "choice",
        "instructions": "Does the text center on the economy?",
        "criteria": {
            "yes": (
                "economy: finance, companies, investment, jobs, prices, trade / "
                "finanzas, empresas, inversion, empleo, precios, comercio"
            ),
            "no": _NO_OPTION,
        },
    },
}


class TopicClassifier:
    """Multi-label topics via one five-question binary pass.

    A single agent.predict() carries all five questions (one forward
    pass against the already-loaded shared model). A category becomes a
    label when its yes-probability clears the threshold, and the stored
    score is that probability, so downstream sorting stays meaningful.
    Definition order is preserved for stable UI badges.
    """

    name = CLASSIFIER_NAME

    def __init__(self, agent=None, yes_threshold: float = DEFAULT_YES_THRESHOLD) -> None:
        # Injectable for tests/scripts; production shares LayaRuntime's lazy agent.
        self._agent = agent
        self.yes_threshold = yes_threshold

    def classify(self, text: str, lang: str = "es") -> list[ClassificationResult]:
        agent = self._agent if self._agent is not None else LayaRuntime.agent()
        result = agent.predict(text, _TOPIC_QUESTIONS)
        answers = result["answers"]
        return [
            ClassificationResult(label=key, score=float(answers[key]["probabilities"]["yes"]))
            for key in _TOPIC_QUESTIONS
            if float(answers[key]["probabilities"]["yes"]) >= self.yes_threshold
        ]
