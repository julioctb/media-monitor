"""Event clustering: token-Jaccard similarity and the 48h window assigner."""

import itertools
from datetime import datetime, timedelta, timezone

from app.ingest.events import assign_mention_to_event, similarity
from app.models import Event, Mention, MentionSource, queries

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
_seq = itertools.count(1)


def _client(session) -> int:
    return queries.get_or_create_client(session, "acme").id


def _assign(session, client_id: int, title: str, when) -> Event:
    """Ingest-shaped helper: insert a mention, run the assigner, return event."""
    n = next(_seq)
    mention = Mention(
        client_id=client_id,
        source=MentionSource.news_rss,
        url=f"https://example.com/{n}",
        url_hash=f"hash{n}",
        title=title,
        published_at=when,
    )
    session.add(mention)
    session.flush()
    assign_mention_to_event(session, mention)
    session.commit()
    session.expire(mention.event)
    return mention.event


def test_similarity_groupes_reordered_titles() -> None:
    score = similarity(
        "BUAP inaugura edificio en Zacapoaxtla",
        "Edificio inaugurado en Zacapoaztla por la BUAP",
    )
    assert score >= 0.5


def test_similarity_distinct_titles_stay_apart() -> None:
    assert (
        similarity(
            "BUAP inaugura edificio en Zacapoaxtla",
            "Sube el dólar frente al peso esta semana",
        )
        < 0.3
    )


def test_similarity_empty_tokens_is_zero() -> None:
    assert similarity("de la", "por el") == 0.0


def test_find_or_create_groups_within_window(session) -> None:
    client_id = _client(session)
    first = _assign(session, client_id, "BUAP inaugura edificio en Zacapoaxtla", T0)
    second = _assign(
        session,
        client_id,
        "Edificio inaugurado en Zacapoaztla por la BUAP",
        T0 + timedelta(hours=10),
    )
    assert second.id == first.id
    assert session.query(Event).count() == 1
    # SQLite roundtrips naive datetimes; compare instant, not tzinfo.
    assert second.first_seen_at.replace(tzinfo=timezone.utc) == T0
    assert second.last_seen_at.replace(tzinfo=timezone.utc) == T0 + timedelta(hours=10)
    assert second.mention_count == 2


def test_find_or_creates_new_event_outside_window(session) -> None:
    client_id = _client(session)
    first = _assign(session, client_id, "BUAP inaugura edificio en Zacapoaxtla", T0)
    later = _assign(
        session, client_id, "BUAP inaugura edificio en Zacapoaxtla",
        T0 + timedelta(hours=72),
    )
    assert later.id != first.id
    assert session.query(Event).count() == 2


def test_events_never_cross_clients(session) -> None:
    client_id = _client(session)
    other_id = queries.get_or_create_client(session, "otro").id
    first = _assign(session, client_id, "BUAP inaugura edificio en Zacapoaxtla", T0)
    other = _assign(session, other_id, "BUAP inaugura edificio en Zacapoaxtla", T0)
    assert other.id != first.id
    assert session.query(Event).count() == 2


def test_canonical_title_is_longest_seen(session) -> None:
    client_id = _client(session)
    _assign(session, client_id, "BUAP inaugura edificio", T0)
    event = _assign(
        session,
        client_id,
        "La BUAP inaugura un edificio nuevo en Zacapoaxtla",
        T0 + timedelta(hours=1),
    )
    assert event.title == "La BUAP inaugura un edificio nuevo en Zacapoaxtla"


def test_mention_counters_and_sources_update_on_assign(session) -> None:
    client_id = _client(session)
    event = _assign(session, client_id, "BUAP inaugura edificio en Zacapoaxtla", T0)
    # Second mention from a different source, same story.
    mention = Mention(
        client_id=client_id,
        source=MentionSource.gdelt,
        url="https://example.com/other",
        url_hash="hash-other",
        title="BUAP inaugura edificio en Zacapoaxtla",
        published_at=T0 + timedelta(minutes=5),
    )
    session.add(mention)
    session.flush()
    assign_mention_to_event(session, mention)
    session.commit()
    session.expire(event)
    assert event.mention_count == 2
    assert event.source_count == 2
