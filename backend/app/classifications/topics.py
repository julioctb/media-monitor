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

#: Classification v2 label set (odd/tasks/classification-v2.md). Single source
#: of truth: the enrichment prompt, the laya fallback criteria and the
#: frontend label maps all mirror these keys.
TOPIC_LABELS = (
    "academic",
    "infrastructure",
    "institutional",
    "students",
    "culture",
    "sports",
    "finance",
    "government",
    "health",
)

# One nine-way choice (v2, corpus-grounded: see odd/tasks/classification-v2.md).
# Tie-breakers live in the criteria: the NATURE of the fact wins over the
# protagonist (an opening led by the rectora is infrastructure, not
# institutional; an institutional budget bump is finance, not government).
_TOPIC_QUESTION = {
    TOPIC_KEY: {
        "type": "choice",
        "instructions": (
            "Which ONE topic dominates the piece? One only. Hard rules: "
            "(A) Physical works and spaces -- edificio, aulas, laboratorios, "
            "campus, mural, obra, inauguracion o entrega de un espacio -- are "
            "ALWAYS infrastructure, even if students benefit or art is "
            "involved. "
            "(B) culture ONLY for artistic/cultural events: festivals, "
            "concerts, performances, traditions, books, film -- NOT buildings, "
            "NOT artworks installed on campus. "
            "(B2) sports when the sport itself is the subject: matches, "
            "results, teams, tournaments, athletes, races. "
            "(C) students ONLY when students are the subject: they win, "
            "protest, receive scholarships, exchange, admission. A rector's "
            "message or an institutional ceremony is NOT students even if "
            "addressed to them. "
            "(D) institutional for governance: informes, nombramientos, "
            "consejo, tramites y documentos, jubilaciones, pensiones, "
            "aniversarios, internal disputes, continuity announcements. "
            "(E) academic for research content: congresos cientificos, "
            "investigacion, publicaciones, ponencias, ciencia. "
            "(F) finance for money figures: presupuesto, inversion, aportaciones, recursos. "
            "(G) government for external officials (state/municipal/federal) "
            "acting around the university. "
            "(H) health for medicine, diseases, healthcare, medical devices. "
            "Examples: 'inaugura edificio en Zacapoaxtla'=infrastructure; "
            "'develan mural en el Complejo Regional'=infrastructure; "
            "'rinde su primer informe'=institutional; 'toma protesta a "
            "funcionarios'=institutional; "
            "'estudiantes ganan concurso de IA'=students; 'recibe 268 "
            "estudiantes de movilidad'=students; "
            "'congreso de microbiologia'=academic; 'debate los retos de la "
            "investigacion'=academic; "
            "'Lobos BUAP victoria en segunda division'=sports; 'festival de "
            "calaveras'=culture; "
            "'anuncia inversion de 160 millones'=finance; 'aportacion estatal "
            "al presupuesto'=finance; "
            "'Armenta respalda a la BUAP'=government; 'dispositivo para "
            "prevenir enfermedades'=health."
        ),
        "criteria": {
            "academic": (
                "Research, congresses, publications, patents, academic bodies, "
                "labs / investigacion, congresos, publicaciones, cuerpo academico"
            ),
            "infrastructure": (
                "Construction works: buildings, campuses, remodelations, "
                "murals, regional complexes, installations / obras, edificios, "
                "campus, instalaciones"
            ),
            "institutional": (
                "University governance and management: reports, appointments, "
                "council, anniversaries, procedures, documents, retirees, "
                "purely ceremonial acts / gobierno interno: informes, "
                "nombramientos, consejo, tramites, aniversarios"
            ),
            "students": (
                "Student life: scholarships, mobility, exchange, admissions, "
                "student achievements, student protests / becas, movilidad, "
                "admision, logros o protestas estudiantiles"
            ),
            "culture": (
                "Cultural events at the institution: art, music, film, "
                "festivals, traditions / cultura: arte, musica, festivales, "
                "tradiciones"
            ),
            "sports": (
                "Sports at the center: games, results, teams, tournaments, "
                "races / deporte: partidos, resultados, equipos, torneos"
            ),
            "finance": (
                "Institutional money: budget, investment, donations, "
                "scholarship funding, resources / presupuesto, inversion, "
                "recursos, convenios economicos"
            ),
            "government": (
                "Relation with external government (state, municipal, "
                "federal): officials, agreements, public policy, lawsuits "
                "vs authorities / relacion con gobiernos externos"
            ),
            "health": (
                "Health at the center: medicine, hospitals, diseases, "
                "vaccines, healthcare research / salud: medicina, hospitales, "
                "enfermedades"
            ),
            OTHER_LABEL: (
                "No area dominates, or pure announcement without a subject / "
                "sin area dominante o aviso puro"
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
