"""build_digest_facts: deterministic facts per client-day. No LLM, no prose."""

from datetime import date, datetime, timezone

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
        title=kw.get("title", "t"),
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
    assert {s["source"] for s in item["sources"]} == {"news_rss", "rss_custom"}
    assert item["topic"] == "institutional"


def test_loose_mention_without_event_is_baja_and_own_item(session) -> None:
    client_id = _client(session)
    loose = _mention(session, client_id, "https://a/solo", title="Suelta")
    _classify(session, loose.id, "topic", "culture")

    facts = build_digest_facts(session, client_id=client_id, day=DAY, tz=TZ)

    assert len(facts["noticias"]) == 1
    assert facts["noticias"][0]["confidence"] == "baja"
    assert facts["noticias"][0]["event_id"] is None
    assert facts["noticias"][0]["topic"] == "culture"


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


def test_rectora_section_from_focus_person(session) -> None:
    from app import persons as persons_mod
    from app.models import Sentiment

    client_id = _client(session)
    mention = _mention(
        session,
        client_id,
        "https://a/rec",
        title="Rectora inaugura",
        sentiment=Sentiment.positive,
    )
    mention.raw_enrichment = {
        "summary": "s",
        "sentiment": "positive",
        "sentiment_score": 0.9,
        "persons": [{"name": "Lilia Cedillo Ramírez"}],
        "topics": [],
    }
    persons_mod.persist_persons_from_enrichment(session, mention)
    session.commit()
    from app.models import Person

    person = session.query(Person).one()
    upsert_settings(session, client_id, {})

    facts = build_digest_facts(
        session, client_id=client_id, day=DAY, tz=TZ, focus_person_id=person.id
    )

    assert facts["rectora"]["person_id"] == person.id
    assert facts["rectora"]["mention_count"] == 1
    assert facts["rectora"]["tone"] == "positive"
    assert facts["personas"][0]["person_id"] == person.id
