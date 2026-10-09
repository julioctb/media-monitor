"""Laya-based sentiment analyzer (Apache-2.0, self-hosted, CPU-friendly).

Laya is a typed-decision encoder: we ask one `choice` question whose
options are positive/neutral/negative with short bilingual descriptions,
and read back the calibrated probability of the chosen option.

The model (~421M params, multilingual subfolder) loads LAZILY on first
analyze() call. Unit tests must inject a mock analyzer — importing this
module never downloads anything.
"""

import logging

from app.ingest.matching import fold_text
from app.models.base import Sentiment
from app.sentiment.base import SentimentAnalyzer, SentimentResult

log = logging.getLogger("sentiment.laya")

MODEL_ID = "convaiinnovations/laya"
# The multilingual checkpoint handles Spanish (the root checkpoint is English).
SUBFOLDER = "multilingual"

_SENTIMENT_QUESTION = {
	"sentiment": {
		"type": "choice",
		"instructions": (
			"What is the sentiment towards the brand or topic that the text mentions? "
			"Judge the SUBJECT, not the event itself. "
			"Evalúa al sujeto, no el evento."
		),
		"criteria": {
			"positive": (
				"Praise, achievements, or news favorable to the subject / "
				"elogio, logros o noticia favorable al sujeto"
			),
			"neutral": (
				"Factual reporting, no clear opinion about the subject "
				"(adverse events told neutrally count) / reporte factual sin "
				"opinión sobre el sujeto (eventos adversos neutrales cuentan)"
			),
			"negative": (
				"Criticism of the subject: complaints, scandals, reputational "
				"damage / crítica al sujeto: quejas, escándalos, daño "
				"reputacional"
			),
		},
	}
}

_LABEL_TO_SENTIMENT = {
    "positive": Sentiment.positive,
    "neutral": Sentiment.neutral,
    "negative": Sentiment.negative,
}


class LayaAnalyzer(SentimentAnalyzer):
    """Sentiment via Laya's choice primitive; lazy single model load."""

    def __init__(self, agent=None) -> None:
        # `agent` injectable for tests / preloaded runtimes. Never construct
        # the real one here — that would download the model at import time.
        self._agent = agent
        self._loaded = agent is not None

    @property
    def loaded(self) -> bool:
        return self._loaded

    def _ensure_agent(self):
        if self._agent is None:
            import laya  # heavy: torch + transformers + weights download

            log.info("loading laya model %s [%s] (first use)", MODEL_ID, SUBFOLDER)
            self._agent = laya.load(MODEL_ID, subfolder=SUBFOLDER)
            self._loaded = True
        return self._agent

    def analyze(self, text: str, lang: str) -> SentimentResult:
        agent = self._ensure_agent()
        result = agent.predict(text, _SENTIMENT_QUESTION)
        answer = result["answers"]["sentiment"]
        label = _LABEL_TO_SENTIMENT[answer["choice"]]
        score = float(answer["probabilities"][answer["choice"]])
        return SentimentResult(label=label, score=score)


class KeywordBaselineAnalyzer(SentimentAnalyzer):
    """Trivial fallback: accent-insensitive positive/negative word counting.

    No model, no download. Good enough to keep the pipeline testable when
    the Laya package cannot be installed; NOT production quality — sarcasm
    and negation are beyond it by design.
    """

    _POSITIVE = frozenset(
        w.strip()
        for w in """
        excelente genial fantástico maravilloso increíble
        buen buena buenos buenas mejor éxito exitoso logro ganar ganaron
        premio orgullo feliz contento agradece agradecido gracias encanta
        encantó amazing awesome great excellent fantastic wonderful best
        better love happy proud success win won award thanks grateful
        congratulations congrats brilliant impressive recommend
        """.split()
        if w.strip()
    )
    _NEGATIVE = frozenset(
        w.strip()
        for w in """
        mal malo mala males peor terrible horroroso pésimo fatal fracaso
        queja quejó problema problemas error errores falla falló hundió
        corrupción corrupto fraude estafa denuncia crisis scandal escándalo
        enojo enojado furia triste lamentable muerte accidente accidentó
        bad worse worst terrible awful horrible disaster failure problem
        problems error broken scam fraud angry sad death accident complaint
        disappointing disappointed useless refuse denied
        """.split()
        if w.strip()
    )

    def analyze(self, text: str, lang: str) -> SentimentResult:
        words = fold_text(text).split()
        pos = sum(1 for w in words if w in self._POSITIVE)
        neg = sum(1 for w in words if w in self._NEGATIVE)
        if pos > neg:
            label = Sentiment.positive
            strength = pos - neg
        elif neg > pos:
            label = Sentiment.negative
            strength = neg - pos
        else:
            return SentimentResult(label=Sentiment.neutral, score=0.5)
        # Bounded confidence: more net polarity words -> more confident.
        score = min(0.9, 0.5 + 0.15 * strength)
        return SentimentResult(label=label, score=score)
