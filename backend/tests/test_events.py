"""Event clustering: token-Jaccard similarity and the 48h window assigner."""

import itertools
from datetime import datetime, timedelta, timezone

from app.ingest.events import (
    assign_mention_to_event,
    similarity,
    similarity_with_suffix_variants,
)
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


def test_suffix_variants_merge_outlet_branded_titles() -> None:
    """Real 15-day sweep case: same story, outlet suffix + truncated title.

    Raw similarity is 0.462 (< 0.5 threshold); stripping the outlet
    suffixes lifts it over the line.
    """
    a = (
        "BUAP reúne a especialistas para analizar el impacto de la "
        "Inteligencia Artificial en la Química - Curul Puebla"
    )
    b = (
        "BUAP reúne a especialistas para analizar el impacto de la "
        "inteligen... - Contraparte | Periodismo en Equilibrio"
    )
    assert similarity(a, b) < 0.5
    assert similarity_with_suffix_variants(a, b) >= 0.5


def test_suffix_variants_keeps_distinct_titles_apart() -> None:
    assert (
        similarity_with_suffix_variants(
            "BUAP inaugura edificio en Zacapoaxtla - El Heraldo",
            "Sube el dólar frente al peso esta semana - Notimex",
        )
        < 0.3
    )


def test_suffix_variants_never_scores_below_plain_similarity() -> None:
    a = "BUAP registra tortuga nueva en Puebla"
    b = "BUAP registra tortuga nueva en Puebla - El Popular"
    plain = similarity(a, b)
    assert similarity_with_suffix_variants(a, b) >= plain


def test_assign_merges_same_story_across_outlet_suffixes(session) -> None:
    """The Emiliano Zapata sweep pair: two outlets, one story, one event."""
    client_id = _client(session)
    first = _assign(
        session,
        client_id,
        "Acusan a profesor de la prepa Emiliano Zapata de la BUAP de acoso"
        " - Ambas Manos",
        T0,
    )
    second = _assign(
        session,
        client_id,
        "Acusan a profesor de la Prepa Zapata de la BUAP de presunto acoso"
        " sexual - Reto Diario",
        T0 + timedelta(hours=3),
    )
    assert second.id == first.id
    assert session.query(Event).count() == 1


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


def test_assign_recovers_when_canonical_drifts(session) -> None:
    """T1 (drift fix): a new headline matching an OLD pool title joins the
    event even when the canonical has drifted to a longer, differently
    worded variant (the finanzas 23-24 split, measured 0.636 on titles)."""
    client_id = _client(session)
    first = _assign(
        session, client_id,
        "Trabajadores de la BUAP pagan por estacionamiento",
        T0,
    )
    # A longer paraphrase joins (0.5 exactly) and becomes the canonical.
    second = _assign(
        session, client_id,
        "Trabajadores de la BUAP pagan por estacionamiento tras convenio"
        " con rectoría y Sindicato",
        T0 + timedelta(hours=3),
    )
    assert second.id == first.id
    # A third outlet repeats the ORIGINAL wording: scores ~0.4 against the
    # drifted canonical but ~0.67 against the original pool title.
    third = _assign(
        session, client_id,
        "Trabajadores de la BUAP pagan por estacionamiento en Ciudad"
        " Universitaria - Diario Cambio",
        T0 + timedelta(hours=5),
    )
    assert third.id == first.id
    assert session.query(Event).count() == 1


def test_pool_matching_keeps_distinct_stories_apart(session) -> None:
    """The pool only widens matching for SAME-story variants: a distinct
    story sharing one token (BUAP) still gets its own event."""
    client_id = _client(session)
    _assign(
        session, client_id,
        "Trabajadores de la BUAP pagan por estacionamiento",
        T0,
    )
    _assign(
        session, client_id,
        "Trabajadores de la BUAP pagan por estacionamiento tras convenio"
        " con rectoría y Sindicato",
        T0 + timedelta(hours=3),
    )
    other = _assign(
        session, client_id,
        "Lobos BUAP conquista el titulo nacional de baloncesto - El Popular",
        T0 + timedelta(hours=6),
    )
    assert session.query(Event).count() == 2
    assert other.id != 1
