"""build_digest_facts: deterministic facts per client-day. No LLM, no prose."""

from datetime import date, datetime, timedelta, timezone

import pytest

from app.models import Client, Event, MentionClassification, MentionSource
from app.models.queries import upsert_settings
from app.summaries.digest import build_digest_facts

DAY = date(2026, 10, 17)
TZ = "America/Mexico_City"
# Noon CST == 18:00 UTC, inside the day window wherever it lands.
NOON = datetime(2026, 10, 17, 18, 0, tzinfo=timezone.utc)


def _client(session) -> int:
    client = Client(name="t")
    session.add(client)
    session.commit()
    return client.id


def _mention(session, client_id: int, url: str, **kw):
    from app.models import Mention, make_url_hash

    mention = Mention(
        client_id=client_id,
        source=kw.get("source", MentionSource.news_rss),
        url=url,
        url_hash=make_url_hash(url),
        title=kw.get("title", "Publicación de seguimiento institucional"),
        summary=kw.get("summary"),
        published_at=kw.get("published_at", NOON),
        ingested_at=kw.get("published_at", NOON),
        event_id=kw.get("event_id"),
        sentiment=kw.get("sentiment"),
    )
    session.add(mention)
    session.commit()
    return mention


def _classify(session, mention_id: int, classifier: str, label: str) -> None:
    session.add(
        MentionClassification(
            mention_id=mention_id, classifier=classifier, label=label, score=0.9
        )
    )
    session.commit()


def test_groups_event_with_confidence_and_sources(session) -> None:
    client_id = _client(session)
    event = Event(
        client_id=client_id,
        title="BUAP inaugura edificio en Zacapoaxtla",
        title_tokens="buap inaugura edificio",
        mention_count=2,
        source_count=2,
        first_seen_at=NOON,
        last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    one = _mention(session, client_id, "https://a/1", event_id=event.id)
    two = _mention(
        session, client_id, "https://b/2", source=MentionSource.rss_custom, event_id=event.id
    )
    _classify(session, one.id, "topic", "institutional")
    _classify(session, two.id, "topic", "institutional")

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert facts["coverage"]["total"] == 2
    assert facts["coverage"]["by_source"] == {"news_rss": 1, "rss_custom": 1}
    item = facts["noticias"][0]
    assert item["event_id"] == event.id
    assert item["confidence"] == "media"  # 2 independent outlets
    assert item["when_label"] == "17 oct."  # local-day stamp from the mention
    assert {s["source"] for s in item["sources"]} == {"news_rss", "rss_custom"}
    assert item["topic"] == "institutional"


def test_event_carries_the_sentiment_mix_for_the_narrative(session) -> None:
    """tone per noticia: the negative-dominance signal the headline weighs."""
    from app.models import Sentiment

    client_id = _client(session)
    event = Event(
        client_id=client_id,
        title="Reforma de pensiones en revisión",
        title_tokens="reforma pensiones",
        mention_count=3,
        source_count=2,
        first_seen_at=NOON,
        last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    for idx, (sentiment, source) in enumerate(
        (
            (Sentiment.negative, MentionSource.news_rss),
            (Sentiment.negative, MentionSource.gdelt),
            (Sentiment.positive, MentionSource.x_twitter),
        )
    ):
        mention = _mention(
            session,
            client_id,
            f"https://s/{idx}-{sentiment.value}",
            source=source,
            sentiment=sentiment,
            event_id=event.id,
        )
        _classify(session, mention.id, "topic", "institutional")

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert facts["noticias"][0]["tone"] == {"negative": 2, "positive": 1}


def test_loose_mention_without_event_is_baja_and_own_item(session) -> None:
    client_id = _client(session)
    loose = _mention(
        session,
        client_id,
        "https://a/solo",
        title="Suelta",
        summary="La publicación anuncia un taller cultural gratuito.",
    )
    _classify(session, loose.id, "topic", "culture")

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert len(facts["noticias"]) == 1
    assert facts["noticias"][0]["confidence"] == "baja"
    assert facts["noticias"][0]["event_id"] is None
    assert facts["noticias"][0]["topic"] == "culture"
    assert facts["noticias"][0]["summary"] == loose.summary


def test_out_of_window_mention_ignored_and_gaps_listed(session) -> None:
    from datetime import timedelta

    client_id = _client(session)
    _mention(
        session,
        client_id,
        "https://a/old",
        published_at=NOON - timedelta(days=3),
    )
    upsert_settings(session, client_id, {})

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert facts["coverage"]["total"] == 0
    assert facts["noticias"] == []
    assert any("Facebook" in g for g in facts["coverage"]["gaps"])
    assert any("X" in g for g in facts["coverage"]["gaps"])


def test_person_ids_are_person_not_link_ids(session) -> None:
    """Regression: person_links are MentionPerson rows; ids diverge quickly.

    Two links on the first mention make the next link id (3) differ from
    the person id (1); the digest must report person ids, never link ids.
    """
    from app import persons as persons_mod
    from app.models import Person

    client_id = _client(session)
    first = _mention(session, client_id, "https://a/1", title="Dos personas")
    first.raw_enrichment = {
        "summary": "s",
        "sentiment": "positive",
        "sentiment_score": 1,
        "persons": [{"name": "Uno"}, {"name": "Dos"}],
        "topics": [],
    }
    persons_mod.persist_persons_from_enrichment(session, first)
    second = _mention(session, client_id, "https://a/2", title="Repetida")
    second.raw_enrichment = {
        "summary": "s",
        "sentiment": "positive",
        "sentiment_score": 1,
        "persons": [{"name": "Uno"}],
        "topics": [],
    }
    persons_mod.persist_persons_from_enrichment(session, second)
    session.commit()

    uno = session.query(Person).filter_by(name="Uno").one()
    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    ids = {p["person_id"] for p in facts["personas"]}
    assert ids == {p.id for p in session.query(Person).all()}
    uno_row = next(p for p in facts["personas"] if p["person_id"] == uno.id)
    assert uno_row["mention_count"] == 2


def test_event_material_comes_from_its_window_publication(session):
    """A stale global budget summary must not accompany today's doctors."""
    from datetime import timedelta

    client_id = _client(session)
    event = Event(
        client_id=client_id,
        title="BUAP anuncia presupuesto para infraestructura 2027",
        title_tokens="buap presupuesto",
        summary="El presupuesto global asigna recursos para infraestructura.",
        first_seen_at=NOON - timedelta(days=3),
        last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    _mention(
        session,
        client_id,
        "https://medio.test/presupuesto",
        event_id=event.id,
        title=event.title,
        summary=event.summary,
        published_at=NOON - timedelta(days=3),
    )
    current = _mention(
        session,
        client_id,
        "https://medio.test/doctores",
        event_id=event.id,
        title="BUAP reconoce a nuevos doctores",
        summary="La universidad entregó reconocimientos a nuevos doctores.",
    )

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert facts["coverage"]["total"] == 1
    item = facts["noticias"][0]
    assert (item["title"], item["summary"]) == (current.title, current.summary)
    assert item["sources"] == [
        {
            "source": "news_rss",
            "url": current.url,
            "title": current.title,
        }
    ]
    # Reading a cut never repairs or erases historical event material.
    session.refresh(event)
    assert (
        event.summary == "El presupuesto global asigna recursos para infraestructura."
    )


@pytest.mark.parametrize(
    "case", ["media_first", "latest_time", "id_tie", "social_only"]
)
def test_window_representative_is_media_first_then_latest(session, case):
    client_id = _client(session)
    event = Event(
        client_id=client_id,
        title="Título global que no pertenece al corte",
        title_tokens="global",
        summary="Reseña global que no es evidencia del corte.",
        first_seen_at=NOON,
        last_seen_at=NOON,
    )
    session.add(event)
    session.flush()
    # The intended winner is inserted first except for the explicit id tie.
    first_source = MentionSource.news_rss
    second_source = MentionSource.rss_custom
    second_time = NOON - timedelta(hours=1)
    if case == "media_first":
        second_source = MentionSource.x_twitter
        second_time = NOON + timedelta(hours=1)
    elif case == "id_tie":
        second_time = NOON
    elif case == "social_only":
        first_source = MentionSource.facebook_page
        second_source = MentionSource.x_twitter
    first = _mention(
        session,
        client_id,
        "https://medio.test/primera",
        event_id=event.id,
        source=first_source,
        title="Primera publicación de la consulta",
        summary="La primera publicación informa el aplazamiento.",
    )
    second = _mention(
        session,
        client_id,
        "https://medio.test/segunda",
        event_id=event.id,
        source=second_source,
        title="Segunda publicación de la consulta",
        summary=None,
        published_at=second_time,
    )
    # SQLite reloads naive UTC walls; injected rows can also be aware.
    session.refresh(second)
    first.published_at = NOON
    winner = second if case == "id_tie" else first

    facts = build_digest_facts(
        session,
        client_id=client_id,
        day=DAY,
        tz=TZ,
        mentions=[second, first],
    )

    item = facts["noticias"][0]
    assert (item["title"], item["summary"]) == (winner.title, winner.summary)
    assert item["source_refs"] == [0, 1]
    assert item["material_ref"] == (1 if winner is second else 0)
    assert [source["mention_id"] for source in facts["evidence"]["sources"]] == [
        first.id, second.id
    ]
    assert len(item["sources"]) == 2
    assert facts["coverage"]["total"] == 2


@pytest.mark.parametrize("case", ["loose", "aggregate_event", "mixed_event"])
def test_aggregate_showcases_are_coverage_not_story_material(session, case):
    from app.models import Sentiment

    client_id = _client(session)
    event_id = None
    if case != "loose":
        event = Event(
            client_id=client_id,
            title="Esta es la PORTADA de @Diario",
            title_tokens="portada diario",
            summary="Presupuesto y doctores mezclados.",
            first_seen_at=NOON,
            last_seen_at=NOON,
        )
        session.add(event)
        session.flush()
        event_id = event.id
    material = None
    if case == "mixed_event":
        material = _mention(
            session,
            client_id,
            "https://medio.test/consulta",
            event_id=event_id,
            source=MentionSource.x_twitter,
            title="Se aplaza la consulta de pensiones",
            summary="La consulta no se celebrará en la fecha prevista.",
            sentiment=Sentiment.negative,
        )
    showcase = _mention(
        session,
        client_id,
        "https://medio.test/portada",
        event_id=event_id,
        title="Esta es la PORTADA de @Diario: presupuesto y doctores",
        summary="Presentación de varios asuntos en una portada.",
        published_at=NOON + timedelta(hours=1),
        sentiment=Sentiment.positive,
    )
    _classify(session, showcase.id, "topic", "institutional")

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert facts["coverage"]["total"] == (2 if material else 1)
    assert facts["coverage"]["by_topic"] == {"institutional": 1}
    if material is None:
        assert facts["noticias"] == []
    else:
        item = facts["noticias"][0]
        assert (item["title"], item["summary"]) == (material.title, material.summary)
        assert [source["url"] for source in item["sources"]] == [
            material.url,
            showcase.url,
        ]
        assert item["tone"] == {"negative": 1, "positive": 1}
        assert item["confidence"] == "media"
