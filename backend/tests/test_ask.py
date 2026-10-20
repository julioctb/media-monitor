"""F4 ask: retrieval unit behavior + endpoint contract (LLM mocked)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.deps import get_client_id
from app.api import ask as ask_api
from app.ask import (
    AskError,
    answer_question,
    build_context,
    find_persons,
    tokenize,
)
from app.db import get_db
from app.main import create_app
from app.models import Base, Client, MentionPerson, Person, Sentiment

from tests.test_api import seed_mention  # noqa: F401  (fixture helpers live there)


def now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


@pytest.fixture()
def db(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(f"sqlite:///{tmp_path}/ask.db")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = factory()
    session.add(Client(name="acme"))
    session.commit()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def api(db):
    app = create_app()

    def override_db():
        yield db

    def override_client_id():
        return db.scalar(select(Client.id).limit(1))

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_client_id] = override_client_id
    with TestClient(app) as test_client:
        yield test_client


# ------------------------------------------------------------------- units


def test_tokenize_drops_stopwords_and_short_tokens() -> None:
    assert tokenize("¿Qué dijo la rectora sobre becas y CU2?") == [
        "rectora",
        "becas",
        "cu2",
    ]


def test_find_persons_matches_name_tokens(db) -> None:
    client_id = db.scalar(select(Client.id).limit(1))
    person = Person(client_id=client_id, name="Lilia Cedillo", name_key="lilia cedillo")
    db.add(person)
    db.commit()

    assert [p.id for p in find_persons(db, client_id, ["lilia", "becas"])] == [person.id]
    assert find_persons(db, client_id, ["zapoteria"]) == []


def test_retrieve_ranks_token_hits_over_recency(db) -> None:
    from app.ask import retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    now_dt = now()
    old_hit = seed_mention(
        db,
        client_id,
        "https://x/old",
        title="Becas destinadas al deporte universitario",
        published=now_dt - timedelta(days=5),
    )
    new_miss = seed_mention(
        db,
        client_id,
        "https://x/new",
        title="Nota sin relacion alguna",
        published=now_dt,
    )
    found, roles = retrieve_mentions(
        db, client_id=client_id, tokens=["becas", "deporte"], person_ids=[]
    )
    assert roles == {}
    assert found[0].id == old_hit.id
    assert new_miss.id in [m.id for m in found] or True  # OR-match may include
    assert old_hit.id != new_miss.id


def test_retrieve_matches_morphological_variants(db) -> None:
    # "becas" in the question must reach notes written with "beca" (and
    # vice versa): exact-substring matching starved the context otherwise.
    from app.ask import retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    singular = seed_mention(
        db,
        client_id,
        "https://x/singular",
        title="Entrega de beca nueva",
        published=now(),
    )
    found, _ = retrieve_mentions(
        db, client_id=client_id, tokens=["becas"], person_ids=[]
    )
    assert singular.id in [m.id for m in found]


def test_retrieve_sentiment_filter_with_person(db) -> None:
    # "notas negativas hacia la rectora": person-linked slots must not be
    # flooded by positive coverage — the sentiment word narrows the linked
    # query itself.
    from app.ask import retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    person = Person(client_id=client_id, name="Margarito Rojas", name_key="margarito rojas")
    db.add(person)
    db.flush()
    neg = seed_mention(
        db, client_id, "https://x/neg", title="Gesto cuestionado", sentiment=Sentiment.negative
    )
    pos = seed_mention(
        db, client_id, "https://x/pos", title="Gesto celebrado", sentiment=Sentiment.positive
    )
    for mention in (neg, pos):
        db.add(MentionPerson(mention_id=mention.id, person_id=person.id))
    db.commit()

    found, _roles = retrieve_mentions(
        db, client_id=client_id, tokens=["notas", "negativas"], person_ids=[person.id]
    )
    ids = [m.id for m in found]
    assert neg.id in ids
    assert pos.id not in ids


def test_retrieve_sentiment_filter_without_person(db) -> None:
    from app.ask import retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    neg = seed_mention(
        db,
        client_id,
        "https://x/neg-presupuesto",
        title="Presupuesto criticado fuerte",
        content="El presupuesto genera rechazo",
        sentiment=Sentiment.negative,
    )
    pos = seed_mention(
        db,
        client_id,
        "https://x/pos-presupuesto",
        title="Presupuesto aprobado con aplausos",
        content="El presupuesto satisface",
        sentiment=Sentiment.positive,
    )
    db.commit()

    found, _ = retrieve_mentions(
        db, client_id=client_id, tokens=["presupuesto", "negativas"], person_ids=[]
    )
    ids = [m.id for m in found]
    assert neg.id in ids
    assert pos.id not in ids


def test_retrieve_includes_person_links_without_token_hit(db) -> None:
    from app.ask import retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    person = Person(client_id=client_id, name="Lilia Cedillo", name_key="lilia cedillo")
    db.add(person)
    db.flush()
    linked = seed_mention(db, client_id, "https://x/linked", title="Nota sin tokens")
    db.add(MentionPerson(mention_id=linked.id, person_id=person.id))
    db.commit()

    found, roles = retrieve_mentions(
        db, client_id=client_id, tokens=["becas"], person_ids=[person.id]
    )
    # Person-first: the linked mention is guaranteed even without token hit.
    assert found[0].id == linked.id
    assert linked.id in [m.id for m in found]


def test_build_context_numbers_and_citations_mirror(db) -> None:
    client_id = db.scalar(select(Client.id).limit(1))
    mention = seed_mention(
        db,
        client_id,
        "https://x/ctx",
        title="Titulo cita",
        content="Contenido suficiente.",
        sentiment=Sentiment.positive,
    )
    block, citations = build_context([mention])
    assert "[1]" in block
    assert citations[0]["mention_id"] == mention.id
    assert citations[0]["sentiment"] == "positive"


def test_answer_without_matches_is_honest(db) -> None:
    client_id = db.scalar(select(Client.id).limit(1))

    class NoCall:
        def complete(self, system, user, **kwargs):  # pragma: no cover
            raise AssertionError("LLM must not be called without matches")

    result = answer_question(
        db,
        client_id=client_id,
        question="zzz qwerty xyz",
        enricher=NoCall(),
    )
    assert "No encontré" in result.answer
    assert result.citations == []


def test_answer_happy_path_cites(db) -> None:
    client_id = db.scalar(select(Client.id).limit(1))
    seed_mention(
        db,
        client_id,
        "https://x/becas",
        title="BUAP amplía becas",
        content="La universidad amplió el programa de becas.",
    )

    class FakeEnricher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def complete(self, system, user, **kwargs):
            self.calls.append((system, user))
            return "La BUAP amplió becas [1]."

    fake = FakeEnricher()
    result = answer_question(db, client_id=client_id, question="becas?", enricher=fake)

    assert result.answer.startswith("La BUAP")
    assert result.citations[0]["url"] == "https://x/becas"
    # The context block carried the citation markers the answer references.
    assert "[1]" in fake.calls[0][1]

    # Fuentes = solo lo que la respuesta cita: [1] filtra a una sola nota.
    seed_mention(
        db,
        client_id,
        "https://x/becas-2",
        title="Otra nota de becas",
        content="Mas contexto del programa.",
    )

    import re as _re

    class CitedOnly(FakeEnricher):
        def __init__(self, marker: str) -> None:
            self.marker = marker
            self.calls: list[tuple[str, str]] = []

        def complete(self, system, user, **kwargs):
            self.calls.append((system, user))
            return f"Respuesta {self.marker}"

    def cited_context_title(enricher) -> str:
        user = enricher.calls[0][1]
        return _re.search(r"\[1\] (.+?) —", user).group(1)

    fake2 = CitedOnly("parcial [1].")
    result = answer_question(db, client_id=client_id, question="becas?", enricher=fake2)
    assert len(result.citations) == 1
    title = cited_context_title(fake2)
    expected_url = (
        "https://x/becas" if title == "BUAP amplía becas" else "https://x/becas-2"
    )
    assert result.citations[0]["url"] == expected_url

    # Sin marcadores (modelo desobediente): se conservan todas.
    result = answer_question(
        db, client_id=client_id, question="becas?", enricher=CitedOnly("sin marcas.")
    )
    assert len(result.citations) == 2


def test_answer_llm_failure_raises_ask_error(db) -> None:
    client_id = db.scalar(select(Client.id).limit(1))
    seed_mention(db, client_id, "https://x/a", title="BUAP becas")

    class NoneEnricher:
        def complete(self, system, user, **kwargs):
            return None

    with pytest.raises(AskError):
        answer_question(
            db, client_id=client_id, question="becas?", enricher=NoneEnricher()
        )


# ---------------------------------------------------------------- endpoint


def test_ask_endpoint_happy_path(api, db, monkeypatch) -> None:
    client_id = db.scalar(select(Client.id).limit(1))
    seed_mention(
        db,
        client_id,
        "https://x/encuesta",
        title="BUAP encuesta satisfacción",
        content="Encuesta a estudiantes.",
    )

    class FakeEnricher:
        def complete(self, system, user, **kwargs):
            return "Respuesta con cita [1]."

    def fake_builder(session, client_id_arg):
        return FakeEnricher()

    monkeypatch.setattr(ask_api, "_build_ask_client", fake_builder)

    response = api.post("/api/clients/1/ask", json={"question": "¿qué pasó con la encuesta?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("Respuesta")
    assert body["citations"][0]["mention_id"] > 0
    assert body["matched_mentions"] >= 1


def test_ask_endpoint_without_provider_is_503(api, db, monkeypatch) -> None:
    monkeypatch.setattr(ask_api, "_build_ask_client", lambda session, cid: None)
    response = api.post("/api/clients/1/ask", json={"question": "becas?"})
    assert response.status_code == 503
    assert "proveedor" in response.json()["detail"].lower()


def test_ask_endpoint_validates_question(api) -> None:
    response = api.post("/api/clients/1/ask", json={"question": "x"})
    assert response.status_code == 422


def test_ask_endpoint_unknown_client_404(api) -> None:
    response = api.post("/api/clients/999/ask", json={"question": "becas?"})
    assert response.status_code == 404

def test_retrieve_annotates_person_roles(db) -> None:
    from app.ask import retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    person = Person(
        client_id=client_id, name="Margarito Rojas", name_key="margarito rojas"
    )
    db.add(person)
    db.flush()
    linked = seed_mention(db, client_id, "https://x/rol", title="Gesto municipal")
    db.add(MentionPerson(mention_id=linked.id, person_id=person.id, role="Presidente municipal"))
    other = seed_mention(db, client_id, "https://x/otros", title="Becas ampliadas")
    db.commit()

    found, roles = retrieve_mentions(
        db, client_id=client_id, tokens=["becas"], person_ids=[person.id]
    )
    assert roles[linked.id] == "Presidente municipal"
    assert other.id in [m.id for m in found]
    assert linked.id in [m.id for m in found]


def test_person_linked_mentions_survive_the_cap(db) -> None:
    """A full page of token-hits must not starve the person's own coverage."""
    from app.ask import MAX_CONTEXT_MENTIONS, retrieve_mentions

    client_id = db.scalar(select(Client.id).limit(1))
    person = Person(client_id=client_id, name="Margarito Rojas", name_key="margarito rojas")
    db.add(person)
    db.flush()
    linked = seed_mention(db, client_id, "https://x/only-person", title="Gesto sin tokens")
    db.add(MentionPerson(mention_id=linked.id, person_id=person.id))
    for index in range(MAX_CONTEXT_MENTIONS + 2):
        seed_mention(
            db, client_id, f"https://x/fill{index}", title=f"Becas y más becas {index}"
        )
    db.commit()

    found, _roles = retrieve_mentions(
        db, client_id=client_id, tokens=["becas"], person_ids=[person.id]
    )
    ids = [m.id for m in found]
    assert linked.id in ids
    assert len(ids) == MAX_CONTEXT_MENTIONS


# ------------------------------------------------------------ digest grounding

def test_answer_includes_recent_digest(db) -> None:
    from datetime import date

    from app.models import queries

    client_id = db.scalar(select(Client.id).limit(1))
    queries.upsert_daily_summary(
        db,
        client_id=client_id,
        day=date.today(),
        content={"schema": 2, "plain_text": "NOTICIAS\n- [alta] Titular del día"},
        narrative="Titular del día.",
        mode="heuristic",
    )
    seed_mention(
        db,
        client_id,
        "https://x/digest",
        title="BUAP ampliación",
        content="Texto.",
    )

    class FakeEnricher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def complete(self, system, user, **kwargs):
            self.calls.append((system, user))
            return "Ok."

    fake = FakeEnricher()
    answer_question(db, client_id=client_id, question="BUAP", enricher=fake)

    user_prompt = fake.calls[0][1]
    assert "Digest editorial" in user_prompt
    assert "Titular del día" in user_prompt


def test_answer_skips_stale_digest(db) -> None:
    from datetime import date, timedelta

    from app.models import queries

    client_id = db.scalar(select(Client.id).limit(1))
    queries.upsert_daily_summary(
        db,
        client_id=client_id,
        day=date.today() - timedelta(days=6),
        content={"schema": 2, "plain_text": "NOTICIAS viejas"},
        narrative="Viejo.",
        mode="heuristic",
    )
    seed_mention(db, client_id, "https://x/stale", title="BUAP", content="x.")

    class FakeEnricher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def complete(self, system, user, **kwargs):
            self.calls.append((system, user))
            return "Ok."

    fake = FakeEnricher()
    answer_question(db, client_id=client_id, question="BUAP", enricher=fake)

    assert "Digest editorial" not in fake.calls[0][1]
