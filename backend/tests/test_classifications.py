"""T10: multi-label classifications — model, registry, pipeline, API.

The classifier registry is injectable everywhere (fake agents / fake
classifiers), so none of these tests load a model.
"""

from dataclasses import dataclass

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import pytest

from app.api.deps import get_client_id
from app.api.schemas import MentionPage
from app.classifications.base import ClassificationResult
from app.classifications.political import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    THRESHOLD_ENV,
    PoliticalClassifier,
    default_confidence_threshold,
)
from app.classifications.registry import build_classifiers, classifier_names
from app.classifications.topics import TopicClassifier
from app.db import get_db
from app.ingest.base import RawMention
from app.ingest.pipeline import persist_raw_mentions
from app.main import create_app
from app.models import (
    Base,
    Client,
    Keyword,
    Mention,
    MentionClassification,
    MentionSource,
    queries,
)


class FakeLayaAgent:
    """Stands in for the real agent; records predict() calls."""

    def __init__(self, choice: str = "political", prob: float = 0.87) -> None:
        self.choice = choice
        self.prob = prob
        self.calls: list[tuple[str, dict]] = []

    def predict(self, text: str, question: dict) -> dict:
        self.calls.append((text, question))
        other = "not_political" if self.choice == "political" else "political"
        return {
            "answers": {
                "political": {
                    "choice": self.choice,
                    "probabilities": {
                        self.choice: self.prob,
                        other: round(1 - self.prob, 2),
                    },
                }
            }
        }


class FlakyClassifier:
    name = "flaky"

    def classify(self, text: str, lang: str = "es") -> ClassificationResult:
        raise RuntimeError("model exploded")


class OkClassifier:
    name = "ok"

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, text: str, lang: str = "es") -> ClassificationResult:
        self.calls += 1
        return ClassificationResult(label="ok_label", score=0.5)


# ----------------------------------------------------------------- registry


def test_registry_exposes_political() -> None:
    assert "political" in classifier_names()
    built = build_classifiers(["political"])
    assert isinstance(built[0], PoliticalClassifier)
    assert built[0].name == "political"


def test_build_classifiers_unknown_name() -> None:
    with pytest.raises(KeyError):
        build_classifiers(["nope"])


def test_political_classifier_high_confidence_political() -> None:
    agent = FakeLayaAgent(choice="political", prob=0.87)
    result = PoliticalClassifier(agent=agent).classify(
        "El congreso vota la reforma", lang="es"
    )
    assert result.label == "political"
    assert result.score == 0.87
    text, question = agent.calls[0]
    assert text == "El congreso vota la reforma"
    assert question["political"]["type"] == "choice"
    assert set(question["political"]["criteria"]) == {"political", "not_political"}


def test_political_classifier_high_confidence_not_political() -> None:
    agent = FakeLayaAgent(choice="not_political", prob=0.82)
    result = PoliticalClassifier(agent=agent).classify(
        "Un concierto anuncia fechas", lang="es"
    )
    assert result.label == "not_political"
    assert result.score == 0.82


def test_political_classifier_low_confidence_uncertain_preserves_chosen_score() -> None:
    agent = FakeLayaAgent(choice="political", prob=0.69)
    classifier = PoliticalClassifier(agent=agent, confidence_threshold=0.80)
    result = classifier.classify("La universidad firmó convenio", lang="es")
    assert result.label == "uncertain"
    assert result.score == 0.69


def test_political_classifier_threshold_can_be_configured(monkeypatch) -> None:
    monkeypatch.setenv(THRESHOLD_ENV, "0.80")
    assert default_confidence_threshold() == 0.80
    agent = FakeLayaAgent(choice="not_political", prob=0.75)
    result = PoliticalClassifier(agent=agent).classify(
        "La empresa abre una planta", lang="es"
    )
    assert result.label == "uncertain"


def test_political_classifier_invalid_threshold_falls_back(monkeypatch) -> None:
    monkeypatch.setenv(THRESHOLD_ENV, "nope")
    assert default_confidence_threshold() == DEFAULT_CONFIDENCE_THRESHOLD


# ------------------------------------------------------------------- model


@pytest.fixture()
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def _mention(session, client_id: int, url: str = "https://x/1") -> Mention:
    mention = Mention(
        client_id=client_id,
        source=MentionSource.news_rss,
        url=url,
        url_hash="hash-" + url,
        title="titulo",
        content="contenido",
    )
    session.add(mention)
    session.commit()
    return mention


def test_upsert_classification_replaces_only_own_classifier(session) -> None:
    client = Client(name="acme")
    session.add(client)
    session.commit()
    mention = _mention(session, client.id)

    queries.upsert_classification(
        session, mention_id=mention.id, classifier="political", label="political", score=0.9
    )
    session.commit()
    queries.upsert_classification(
        session, mention_id=mention.id, classifier="political", label="not_political", score=0.4
    )
    session.commit()
    # A second classifier coexists: axes are independent.
    queries.upsert_classification(
        session, mention_id=mention.id, classifier="topic", label="sports", score=0.7
    )
    session.commit()

    rows = session.scalars(
        select(MentionClassification).where(MentionClassification.mention_id == mention.id)
    ).all()
    assert {(r.classifier, r.label) for r in rows} == {
        ("political", "not_political"),
        ("topic", "sports"),
    }


def test_classification_breakdown_is_client_scoped(session) -> None:
    client_a = Client(name="a")
    client_b = Client(name="b")
    session.add_all([client_a, client_b])
    session.commit()
    mention_a = _mention(session, client_a.id, url="https://a/1")
    mention_b = _mention(session, client_b.id, url="https://b/1")
    queries.upsert_classification(
        session, mention_id=mention_a.id, classifier="political", label="political", score=0.9
    )
    queries.upsert_classification(
        session, mention_id=mention_b.id, classifier="political", label="not_political", score=0.4
    )
    session.commit()

    assert queries.classification_breakdown(
        session, client_id=client_a.id, classifier="political"
    ) == {"political": 1}
    assert queries.classification_breakdown(
        session, client_id=client_b.id, classifier="political"
    ) == {"not_political": 1}


def test_list_mentions_filters_by_classifier_and_label(session) -> None:
    client = Client(name="acme")
    session.add(client)
    session.commit()
    political = _mention(session, client.id, url="https://x/pol")
    other = _mention(session, client.id, url="https://x/other")

    queries.upsert_classification(
        session, mention_id=political.id, classifier="political", label="political", score=0.9
    )
    queries.upsert_classification(
        session, mention_id=other.id, classifier="political", label="not_political", score=0.6
    )
    session.commit()

    political_only = queries.list_mentions(
        session, client.id, classifier="political", label="political"
    )
    assert [m.id for m in political_only] == [political.id]

    any_political = queries.list_mentions(session, client.id, classifier="political")
    assert {m.id for m in any_political} == {political.id, other.id}

    # ...and the count path mirrors the list path.
    assert (
        queries.count_mentions(session, client.id, classifier="political", label="political") == 1
    )


def test_classifications_by_mention_groups_batch(session) -> None:
    client = Client(name="acme")
    session.add(client)
    session.commit()
    one = _mention(session, client.id, url="https://x/1")
    two = _mention(session, client.id, url="https://x/2")
    queries.upsert_classification(
        session, mention_id=one.id, classifier="political", label="political", score=0.9
    )
    session.commit()

    grouped = queries.classifications_by_mention(session, [one.id, two.id])
    assert one.id in grouped and two.id not in grouped
    assert grouped[one.id][0].label == "political"
    assert queries.classifications_by_mention(session, []) == {}


# ---------------------------------------------------------------- pipeline


def _client_with_keyword(session):
    client = Client(name="acme")
    session.add(client)
    session.commit()
    keyword = Keyword(client_id=client.id, text="acme", language="es")
    session.add(keyword)
    session.commit()
    return client, keyword


def _raw(url: str, title: str = "acme news") -> RawMention:
    return RawMention(
        source=MentionSource.news_rss, url=url, keyword="acme", title=title, content="cuerpo"
    )


def test_pipeline_runs_classifiers_and_survives_failures(session) -> None:
    client, keyword = _client_with_keyword(session)
    inserted = persist_raw_mentions(
        session,
        client_id=client.id,
        items=[_raw("https://x/1")],
        keyword_by_text={"acme": keyword},
        all_keyword_texts=["acme"],
        classifiers=[FlakyClassifier(), OkClassifier()],
    )
    assert inserted == 1
    mention = session.scalars(select(Mention)).one()
    rows = session.scalars(
        select(MentionClassification).where(MentionClassification.mention_id == mention.id)
    ).all()
    assert [(r.classifier, r.label, r.score) for r in rows] == [("ok", "ok_label", 0.5)]


def test_pipeline_upserts_on_reingest_never_duplicates(session) -> None:
    client, keyword = _client_with_keyword(session)
    for _ in range(2):
        persist_raw_mentions(
            session,
            client_id=client.id,
            items=[_raw("https://x/1")],
            keyword_by_text={"acme": keyword},
            all_keyword_texts=["acme"],
            classifiers=[OkClassifier()],
        )
    rows = session.scalars(select(MentionClassification)).all()
    assert len(rows) == 1  # unique(mention, classifier): re-runs replace


# --------------------------------------------------------------------- api


@pytest.fixture()
def api(tmp_path):
    """TestClient + file-based session (mirror test_api: memory sqlite and
    TestClient's portal thread disagree on connection ownership)."""
    engine = create_engine(f"sqlite:///{tmp_path}/classifications.db")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    client_row = Client(name="acme")
    session.add(client_row)
    session.commit()

    app = create_app()

    def override_db():
        yield session

    def override_client_id():
        return client_row.id

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = override_client_id
    try:
        yield TestClient(app), client_row, session
    finally:
        session.close()
        engine.dispose()


def test_mentions_response_carries_classifications(api) -> None:
    client, client_row, session = api
    mention = _mention(session, client_row.id)
    queries.upsert_classification(
        session, mention_id=mention.id, classifier="political", label="political", score=0.9
    )
    session.commit()

    body = client.get("/api/mentions").json()
    page = MentionPage.model_validate(body)
    assert page.items[0].classifications[0].classifier == "political"

    filtered = client.get(
        "/api/mentions", params={"classifier": "political", "label": "political"}
    ).json()
    assert filtered["total"] == 1

    empty = client.get(
        "/api/mentions", params={"classifier": "political", "label": "not_political"}
    ).json()
    assert empty["total"] == 0


def test_stats_overview_includes_classifier_breakdown(api) -> None:
    client, client_row, session = api
    mention = _mention(session, client_row.id)
    queries.upsert_classification(
        session, mention_id=mention.id, classifier="political", label="political", score=0.9
    )
    session.commit()

    payload = client.get("/api/stats/overview").json()
    political = next(c for c in payload["classifications"] if c["classifier"] == "political")
    assert political["total_classified"] == 1
    assert political["breakdown"] == {"political": 1}


# ------------------------------------------------------- topics (T12)


class FakeChoiceAgent:
    """Stands in for the agent's choice question: scripted (choice, prob)."""

    def __init__(self, *calls: tuple[str, float]) -> None:
        self.script = list(calls)
        self.calls: list[tuple[str, dict]] = []

    def predict(self, text: str, questions: dict) -> dict:
        self.calls.append((text, questions))
        choice, prob = self.script.pop(0) if self.script else ("other", 0.0)
        answers = {}
        for key, spec in questions.items():
            options = list(spec["criteria"])
            loser = round((1 - prob) / max(len(options) - 1, 1), 2)
            answers[key] = {
                "choice": choice,
                "probabilities": {
                    option: (prob if option == choice else loser) for option in options
                },
            }
        return {"answers": answers}


class MultiLabelClassifier:
    name = "multi"

    def classify(self, text: str, lang: str = "es") -> list[ClassificationResult]:
        return [
            ClassificationResult(label="sports", score=0.9),
            ClassificationResult(label="culture", score=0.6),
        ]


TOPIC_OPTIONS = {"sports", "academic", "culture", "health", "economy", "other"}


def test_topic_classifier_returns_single_dominant_label() -> None:
    agent = FakeChoiceAgent(("sports", 0.87))
    result = TopicClassifier(agent=agent).classify("Pumas gana el clasico", lang="es")
    # One label only: the dominant theme, scored with its own probability.
    assert result == ClassificationResult(label="sports", score=0.87)
    # One predict call carrying the single six-way choice question.
    assert len(agent.calls) == 1
    text, question = agent.calls[0]
    assert text == "Pumas gana el clasico"
    assert set(question) == {"topic"}
    assert question["topic"]["type"] == "choice"
    assert set(question["topic"]["criteria"]) == TOPIC_OPTIONS
    instructions = question["topic"]["instructions"].lower()
    assert "domin" in instructions  # dominant-theme rule, EN and ES
    assert "institucional" in instructions  # institutional/corporate -> other


def test_topic_classifier_other_means_no_result() -> None:
    agent = FakeChoiceAgent(("other", 0.6))
    # other = sin tema: empty result, so the pipeline stores no row.
    assert TopicClassifier(agent=agent).classify("nota corporativa", lang="es") == []


def test_registry_exposes_topic() -> None:
    assert "topic" in classifier_names()
    built = build_classifiers(["topic"])
    assert isinstance(built[0], TopicClassifier)
    assert built[0].name == "topic"


def test_upsert_classifications_multi_label_replaces_only_own_rows(session) -> None:
    client = Client(name="acme")
    session.add(client)
    session.commit()
    mention = _mention(session, client.id)

    queries.upsert_classification(
        session, mention_id=mention.id, classifier="political", label="political", score=0.9
    )
    queries.upsert_classifications(
        session,
        mention_id=mention.id,
        classifier="multi",
        results=[("sports", 0.9), ("culture", 0.6)],
    )
    session.commit()

    def stored_rows() -> set[tuple[str, str]]:
        rows = session.scalars(
            select(MentionClassification).where(
                MentionClassification.mention_id == mention.id
            )
        ).all()
        return {(r.classifier, r.label) for r in rows}

    assert stored_rows() == {
        ("political", "political"),
        ("multi", "sports"),
        ("multi", "culture"),
    }

    # Re-running the classifier replaces all of its rows; political stays.
    queries.upsert_classifications(
        session, mention_id=mention.id, classifier="multi", results=[("sports", 0.7)]
    )
    session.commit()
    assert stored_rows() == {("political", "political"), ("multi", "sports")}


def test_multi_label_mention_matches_each_label_filter(session) -> None:
    client = Client(name="acme")
    session.add(client)
    session.commit()
    mention = _mention(session, client.id)
    queries.upsert_classifications(
        session,
        mention_id=mention.id,
        classifier="multi",
        results=[("sports", 0.9), ("culture", 0.6)],
    )
    session.commit()

    for label in ("sports", "culture"):
        found = queries.list_mentions(session, client.id, classifier="multi", label=label)
        assert [m.id for m in found] == [mention.id]
        assert (
            queries.count_mentions(session, client.id, classifier="multi", label=label) == 1
        )

    assert queries.list_mentions(
        session, client.id, classifier="multi", label="health"
    ) == []
    # Classifier alone matches any of the mention's labels.
    assert {m.id for m in queries.list_mentions(session, client.id, classifier="multi")} == {
        mention.id
    }


def test_classification_breakdown_counts_every_label(session) -> None:
    client = Client(name="acme")
    session.add(client)
    session.commit()
    one = _mention(session, client.id, url="https://x/1")
    two = _mention(session, client.id, url="https://x/2")
    queries.upsert_classifications(
        session, mention_id=one.id, classifier="multi", results=[("sports", 0.9), ("culture", 0.6)]
    )
    queries.upsert_classifications(
        session, mention_id=two.id, classifier="multi", results=[("economy", 0.8)]
    )
    session.commit()

    assert queries.classification_breakdown(session, client_id=client.id, classifier="multi") == {
        "sports": 1,
        "culture": 1,
        "economy": 1,
    }


def test_pipeline_stores_multi_label_and_single_classifiers(session) -> None:
    client, keyword = _client_with_keyword(session)
    inserted = persist_raw_mentions(
        session,
        client_id=client.id,
        items=[_raw("https://x/1")],
        keyword_by_text={"acme": keyword},
        all_keyword_texts=["acme"],
        classifiers=[MultiLabelClassifier(), OkClassifier()],
    )
    assert inserted == 1
    rows = session.scalars(select(MentionClassification)).all()
    assert {(r.classifier, r.label, r.score) for r in rows} == {
        ("multi", "sports", 0.9),
        ("multi", "culture", 0.6),
        ("ok", "ok_label", 0.5),
    }


def test_pipeline_empty_result_clearing_is_query_level(session) -> None:
    client, keyword = _client_with_keyword(session)
    persist_raw_mentions(
        session,
        client_id=client.id,
        items=[_raw("https://x/1")],
        keyword_by_text={"acme": keyword},
        all_keyword_texts=["acme"],
        classifiers=[MultiLabelClassifier()],
    )
    # Reingest does not re-classify (created-only); the empty-result clear
    # happens wherever a classifier re-runs, i.e. in the plural upsert.
    mention_id = session.scalars(select(Mention.id)).one()
    queries.upsert_classifications(
        session, mention_id=mention_id, classifier="multi", results=[]
    )
    session.commit()
    rows = session.scalars(
        select(MentionClassification).where(MentionClassification.classifier == "multi")
    ).all()
    assert rows == []


def test_pipeline_topic_stores_one_row_and_other_stores_none(session) -> None:
    client, keyword = _client_with_keyword(session)
    agent = FakeChoiceAgent(("sports", 0.9), ("other", 0.6))
    inserted = persist_raw_mentions(
        session,
        client_id=client.id,
        items=[_raw("https://x/1", "acme deportivo"), _raw("https://x/2", "acme corporativo")],
        keyword_by_text={"acme": keyword},
        all_keyword_texts=["acme"],
        classifiers=[TopicClassifier(agent=agent)],
    )
    assert inserted == 2
    url_by_id = {m.id: m.url for m in session.scalars(select(Mention)).all()}
    rows = session.scalars(
        select(MentionClassification).where(MentionClassification.classifier == "topic")
    ).all()
    # Single-label outcome: sports persists once, other leaves no row.
    assert sorted((url_by_id[r.mention_id], r.label, r.score) for r in rows) == [
        ("https://x/1", "sports", 0.9)
    ]
