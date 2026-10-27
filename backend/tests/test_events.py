"""Event clustering: token-Jaccard similarity and the 48h window assigner."""

import itertools
from datetime import datetime, timedelta, timezone

import pytest

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


@pytest.mark.parametrize("poisoned", ["pool", "canonical"])
def test_legacy_aggregate_cannot_attract_new_publication(session, poisoned):
    """Historical showcases are not identity evidence for new articles."""
    client_id = _client(session)
    legacy = _assign(session, client_id, "Presupuesto federal 2027", T0)
    aggregate = "Esta es la portada de @Medio: Convenio hospital universitario"
    session.add(
        Mention(
            client_id=client_id,
            source=MentionSource.x_twitter,
            url="https://example.test/legacy-showcase",
            url_hash="legacy-showcase",
            title=aggregate,
            event_id=legacy.id,
            published_at=T0,
        )
    )
    if poisoned == "canonical":
        legacy.title = aggregate
    session.commit()
    session.refresh(legacy)
    before = (legacy.title, legacy.mention_count)

    incoming = _assign(
        session, client_id, "Convenio hospital universitario", T0 + timedelta(hours=1)
    )

    assert incoming.id != legacy.id
    session.refresh(legacy)
    assert (legacy.title, legacy.mention_count) == before
    assert session.query(Mention).filter(Mention.event_id == legacy.id).count() == 2
    assert session.query(Event).count() == 2


def test_legacy_aggregate_does_not_drive_deterministic_pair_merge(session):
    """The shared scorer also quarantines aggregate comparison inputs."""
    from app.ingest.arbitrator import merge_deterministic_pairs

    client_id = _client(session)
    legacy = _assign(session, client_id, "Presupuesto federal 2027", T0)
    other = _assign(session, client_id, "Convenio hospital universitario", T0)
    aggregate = "Esta es la portada de @Medio: Convenio hospital universitario"
    legacy.title = aggregate
    session.add(
        Mention(
            client_id=client_id,
            source=MentionSource.x_twitter,
            url="https://example.test/legacy-pair-showcase",
            url_hash="legacy-pair-showcase",
            title=aggregate,
            event_id=legacy.id,
            published_at=T0,
        )
    )
    session.commit()
    identities = {legacy.id, other.id}

    result = merge_deterministic_pairs(
        session, client_id=client_id, now=T0 + timedelta(hours=1)
    )

    assert result == {"deterministic_merged": 0}
    assert {event.id for event in session.query(Event).all()} == identities
    session.refresh(legacy)
    assert legacy.title == aggregate


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


@pytest.mark.parametrize("prefix", ["BUAP", "Instituto Norte"])
@pytest.mark.parametrize(
    "outlets",
    [("", ""), (" - Diario Norte | Local", " - Revista Sur | Sociedad")],
)
def test_substantive_pipe_titles_keep_distinct_public_event_identity(
    session, prefix, outlets
):
    """A shared institution prefix must not replace the actual occurrence."""
    from app.summaries.builder import digest_prompt_view, display_title

    client_id = _client(session)
    clean_titles = [f"{prefix} | Abre biblioteca", f"{prefix} | Cierra hospital"]
    raw_titles = [title + outlet for title, outlet in zip(clean_titles, outlets)]
    assert similarity(*raw_titles) < 0.5
    first = _assign(session, client_id, raw_titles[0], T0)
    second = _assign(session, client_id, raw_titles[1], T0 + timedelta(hours=1))

    assert first.id != second.id
    rows = session.query(Mention).order_by(Mention.id).all()
    assert [row.title for row in rows] == raw_titles
    assert [row.event_id for row in rows] == [first.id, second.id]
    assert session.query(Event).count() == 2
    assert first.mention_count == second.mention_count == 1
    assert [display_title(title) for title in raw_titles] == clean_titles
    facts = {"noticias": [{"title": title} for title in raw_titles]}
    view = digest_prompt_view(facts)
    assert [story["title"] for story in view["noticias"]] == clean_titles
    assert [story["title"] for story in facts["noticias"]] == raw_titles


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
        session,
        client_id,
        "BUAP inaugura edificio en Zacapoaxtla",
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
        session,
        client_id,
        "Trabajadores de la BUAP pagan por estacionamiento",
        T0,
    )
    # A longer paraphrase joins (0.5 exactly) and becomes the canonical.
    second = _assign(
        session,
        client_id,
        "Trabajadores de la BUAP pagan por estacionamiento tras convenio"
        " con rectoría y Sindicato",
        T0 + timedelta(hours=3),
    )
    assert second.id == first.id
    # A third outlet repeats the ORIGINAL wording: scores ~0.4 against the
    # drifted canonical but ~0.67 against the original pool title.
    third = _assign(
        session,
        client_id,
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
        session,
        client_id,
        "Trabajadores de la BUAP pagan por estacionamiento",
        T0,
    )
    _assign(
        session,
        client_id,
        "Trabajadores de la BUAP pagan por estacionamiento tras convenio"
        " con rectoría y Sindicato",
        T0 + timedelta(hours=3),
    )
    other = _assign(
        session,
        client_id,
        "Lobos BUAP conquista el titulo nacional de baloncesto - El Popular",
        T0 + timedelta(hours=6),
    )
    assert session.query(Event).count() == 2
    assert other.id != 1


def test_front_page_showcase_posts_are_quarantined(session) -> None:
    """D1: a portada post aggregates SEVERAL stories' headlines — it must
    never join an event (it bridged presupuesto+pensiones into one)."""
    from app.ingest.events import is_aggregate_title

    client_id = _client(session)
    assert is_aggregate_title(
        "¡Feliz viernes! ☀️ Esta es la PORTADA de @MTPNoticias 🧑‍🏫 Lilia Cedillo"
    )
    assert not is_aggregate_title("Presentan la portada del libro universitario")

    portada_mention = Mention(
        client_id=client_id,
        source=MentionSource.x_twitter,
        url="https://x.com/portada",
        url_hash="portada-hash",
        title=(
            "¡Feliz viernes! Esta es la PORTADA de @MTPNoticias Lilia Cedillo"
            " busca subir sueldo Armenta y Chedraui se reúnen"
        ),
        published_at=T0,
    )
    session.add(portada_mention)
    session.flush()
    assign_mention_to_event(session, portada_mention)
    session.commit()
    # The mention carries no event at all.
    assert portada_mention.event_id is None

    # The two REAL stories the portada mentions stay separate events.
    a = _assign(
        session,
        client_id,
        "Lilia Cedillo busca subir sueldo a maestros de la BUAP",
        T0 + timedelta(hours=1),
    )
    b = _assign(
        session,
        client_id,
        "Armenta y Chedraui se reúnen por la alcaldía",
        T0 + timedelta(hours=2),
    )
    assert a.id != b.id
    assert session.query(Event).filter(Event.client_id == client_id).count() == 2


def test_canonical_prefers_media_over_longer_social(session) -> None:
    """D2: media headlines outrank social mega-titles for the canonical."""
    client_id = _client(session)
    first = _assign(session, client_id, "BUAP pospone consulta de pensiones", T0)
    # A longer SOCIAL title joins the same event (pool match)…
    social = Mention(
        client_id=client_id,
        source=MentionSource.x_twitter,
        url="https://x.com/1",
        url_hash="social-hash",
        title="BUAP pospone consulta de pensiones y anuncia aumento salarial",
        published_at=T0 + timedelta(hours=3),
    )
    session.add(social)
    session.flush()
    assign_mention_to_event(session, social)
    session.commit()
    session.expire(first)
    assert social.event_id == first.id
    # …but the canonical stays the MEDIA headline, not the social mega-title.
    assert first.title == "BUAP pospone consulta de pensiones"
