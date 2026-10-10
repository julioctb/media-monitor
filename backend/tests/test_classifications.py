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
    result = PoliticalClassifier(agent=agent).classify(
        "La universidad firmó convenio", lang="es"
    )
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
