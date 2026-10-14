"""Sentiment analyzer tests. NO model download — Laya agent is mocked."""

import pytest

from app.models.base import Sentiment
from app.sentiment.base import SentimentAnalyzer, SentimentResult
from app.sentiment.laya_analyzer import (
    _SENTIMENT_QUESTION,
    KeywordBaselineAnalyzer,
    LayaAnalyzer,
)


class FakeLayaAgent:
    """Mimics laya.Agent.predict's answer shape (verified against laya 0.3.4)."""

    def __init__(self, choice: str = "positive", prob: float = 0.82) -> None:
        self.choice = choice
        self.prob = prob
        self.calls: list[tuple[str, dict]] = []

    def predict(self, state, questions):
        self.calls.append((state, questions))
        return {
            "answers": {
                "sentiment": {
                    "type": "choice",
                    "choice": self.choice,
                    "probabilities": {
                        "positive": self.prob if self.choice == "positive" else 0.05,
                        "neutral": self.prob if self.choice == "neutral" else 0.05,
                        "negative": self.prob if self.choice == "negative" else 0.05,
                    },
                    "confidence": self.prob,
                }
            }
        }


class TestLayaAnalyzer:
    def test_interface_conformance(self) -> None:
        analyzer = LayaAnalyzer(agent=FakeLayaAgent())
        assert isinstance(analyzer, SentimentAnalyzer)

    def test_lazy_no_model_at_construction(self) -> None:
        analyzer = LayaAnalyzer()
        assert analyzer.loaded is False

    def test_analyze_maps_choice_to_sentiment(self) -> None:
        agent = FakeLayaAgent(choice="negative", prob=0.77)
        analyzer = LayaAnalyzer(agent=agent)
        result = analyzer.analyze("La BUAP es un desastre", "es")
        assert result.label is Sentiment.negative
        assert result.score == 0.77
        # The question sent to laya: choice type, three bilingual options.
        state, questions = agent.calls[0]
        assert state == "La BUAP es un desastre"
        q = questions["sentiment"]
        assert q["type"] == "choice"
        assert set(q["criteria"]) == {"positive", "neutral", "negative"}

    def test_analyze_positive(self) -> None:
        analyzer = LayaAnalyzer(agent=FakeLayaAgent(choice="positive", prob=0.91))
        result = analyzer.analyze("Great news from the brand!", "en")
        assert result.label is Sentiment.positive
        assert result.score == 0.91

    def test_question_shape_stable(self) -> None:
        q = _SENTIMENT_QUESTION["sentiment"]
        assert q["type"] == "choice"
        assert set(q["criteria"].keys()) == {"positive", "neutral", "negative"}
        for desc in q["criteria"].values():
            assert " / " in desc  # bilingual description


class TestKeywordBaselineAnalyzer:
    def test_positive_spanish(self) -> None:
        analyzer = KeywordBaselineAnalyzer()
        assert analyzer.analyze("Excelente noticia de la BUAP, qué genial", "es").label is Sentiment.positive

    def test_negative_spanish_accent_insensitive(self) -> None:
        analyzer = KeywordBaselineAnalyzer()
        r = analyzer.analyze("Un fraude terrible, qué mal servicio", "es")
        assert r.label is Sentiment.negative

    def test_english(self) -> None:
        analyzer = KeywordBaselineAnalyzer()
        assert analyzer.analyze("Amazing product, love it", "en").label is Sentiment.positive
        assert analyzer.analyze("Terrible service, useless", "en").label is Sentiment.negative

    def test_neutral_when_no_polarity_words(self) -> None:
        analyzer = KeywordBaselineAnalyzer()
        r = analyzer.analyze("La BUAP publicó su convocatoria 2026", "es")
        assert r.label is Sentiment.neutral
        assert r.score == 0.5

    def test_tie_is_neutral(self) -> None:
        analyzer = KeywordBaselineAnalyzer()
        r = analyzer.analyze("buena idea pero terrible ejecución", "es")
        assert r.label is Sentiment.neutral

    def test_score_bounded(self) -> None:
        analyzer = KeywordBaselineAnalyzer()
        r = analyzer.analyze("excelente genial fantástico maravilloso increíble", "es")
        assert 0.5 < r.score <= 0.9


class TestLazyLayaAnalyzer:
    """Lazy-optional wiring: nothing Laya-shaped until first analyze()."""

    @pytest.fixture()
    def stub_laya(self, fresh_laya, monkeypatch):
        """Replace the real LayaAnalyzer with a counting stub."""
        import app.sentiment.laya_analyzer as laya_module

        created: list = []

        class StubLaya:
            def __init__(self) -> None:
                self.calls: list[str] = []
                created.append(self)

            def analyze(self, text: str, lang: str) -> SentimentResult:
                self.calls.append(text)
                return SentimentResult(label=Sentiment.neutral, score=0.5)

        monkeypatch.setattr(laya_module, "LayaAnalyzer", StubLaya)
        return created

    def test_lazy_no_construction_at_factory_time(self, stub_laya) -> None:
        from app.sentiment.factory import LazyLayaAnalyzer, build_sentiment_analyzer

        analyzer = build_sentiment_analyzer(provider="local")
        assert isinstance(analyzer, LazyLayaAnalyzer)
        assert analyzer.loaded is False
        assert stub_laya == []  # nothing constructed for the cycle

    def test_materializes_once_on_first_analyze(self, stub_laya) -> None:
        from app.sentiment.factory import shared_laya

        lazy = shared_laya()
        first = lazy.analyze("texto", "es")
        assert first.label is Sentiment.neutral
        assert len(stub_laya) == 1
        assert shared_laya() is lazy  # process-wide singleton
        lazy.analyze("otro", "es")
        assert len(stub_laya) == 1  # reused, never rebuilt
        assert stub_laya[0].calls == ["texto", "otro"]

    def test_api_failure_falls_back_through_lazy_singleton(self, stub_laya) -> None:
        """Enrichment/sentiment failure with the provider down: the first
        actual fallback need materializes the shared lazy analyzer."""
        import httpx

        from app.sentiment.api_analyzer import ApiSentimentAnalyzer
        from app.sentiment.factory import shared_laya

        class FailingClient:
            def post(self, *a, **k):
                raise httpx.ConnectError("provider down")

        ApiSentimentAnalyzer(
            api_key="k",
            fallback=shared_laya(),
            client=FailingClient(),  # type: ignore[arg-type]
            attempts=2,
            backoff_s=0,
        ).analyze("texto", "es")

        assert len(stub_laya) == 1  # exactly one construction, on need
        assert shared_laya().loaded is True
