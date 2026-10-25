"""Event-identity arbitrator: gray-band detection, judgment, merge."""

import itertools
from datetime import datetime, timedelta, timezone

from app.ingest.arbitrator import (
    GrayPair,
    PairVerdict,
    find_gray_pairs,
    merge_events,
    reconcile_gray_pairs,
)
from app.ingest.events import assign_mention_to_event
from app.models import Event, EventMerge, Mention, MentionSource, queries

T0 = datetime(2026, 10, 25, 12, 0, tzinfo=timezone.utc)
_seq = itertools.count(1)

# The measured production grays (25/oct probes): pensiones scored 0.364
# between canonicals; finanzas-parking 0.214 stays below the band.
PENSIONES_A = "BUAP pospone consulta sobre reforma de pensiones y propone aumento salarial"
PENSIONES_B = "BUAP pospone consulta al sistema de pensiones y jubilaciones - Diario Cambio"
FINANZAS_A = "Acuerdo para que trabajadores de Finanzas usen estacionamiento de la Benemérita"
DEPORTES_B = "Lobos BUAP conquista el titulo nacional de baloncesto - El Popular"


def _client(session) -> int:
    return queries.get_or_create_client(session, "acme").id


def _assign(session, client_id: int, title: str, when) -> Event:
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


def _fake_judge(verdicts: dict[tuple[int, int], tuple[bool, str]]):
    """Judge stub honoring the contract: dict of (from,to) -> (mismo, razon)."""

    def judge(pairs: list[GrayPair]) -> dict[tuple[int, int], PairVerdict]:
        return {
            key: PairVerdict(a=key[0], b=key[1], mismo=same, razon=reason)
            for key, (same, reason) in verdicts.items()
            if key in {(p.from_id, p.to_id) for p in pairs}
        }

    return judge


def test_gray_band_detects_paraphrase_and_ignores_clear_pairs(session) -> None:
    client_id = _client(session)
    pensiones = _assign(session, client_id, PENSIONES_A, T0)
    pensiones_b = _assign(session, client_id, PENSIONES_B, T0 + timedelta(hours=6))
    finanzas = _assign(session, client_id, FINANZAS_A, T0 + timedelta(hours=1))
    deportes = _assign(session, client_id, DEPORTES_B, T0 + timedelta(hours=2))

    # The paraphrase pair split into two events (the production bug shape).
    assert pensiones_b.id != pensiones.id
    pairs = find_gray_pairs(session, client_id=client_id, now=T0 + timedelta(hours=8))
    pair_ids = {frozenset((p.from_id, p.to_id)) for p in pairs}
    assert frozenset((pensiones.id, pensiones_b.id)) in pair_ids
    # Clear pairs never reach the judge.
    assert frozenset((finanzas.id, pensiones.id)) not in pair_ids
    assert frozenset((deportes.id, pensiones.id)) not in pair_ids


def test_reconcile_misma_merges_and_records_audit(session) -> None:
    client_id = _client(session)
    a = _assign(session, client_id, PENSIONES_A, T0)
    b = _assign(session, client_id, PENSIONES_B, T0 + timedelta(hours=6))

    judge = _fake_judge({(b.id, a.id): (True, "misma consulta pospuesta")})
    result = reconcile_gray_pairs(
        session, client_id=client_id, now=T0 + timedelta(hours=8), judge=judge
    )
    assert result == {"candidates": 1, "merged": 1, "kept": 0}

    survivor = session.query(Event).filter(Event.client_id == client_id).one()
    assert survivor.id == a.id  # the anchor keeps the lower id on ties
    assert survivor.mention_count == 2
    mentions = session.query(Mention).filter(Mention.client_id == client_id).all()
    assert {m.event_id for m in mentions} == {a.id}
    audit = session.query(EventMerge).one()
    assert audit.event_from == b.id and audit.event_to == a.id
    assert audit.verdict == "misma"


def test_reconcile_distinta_keeps_split_but_memoes(session) -> None:
    client_id = _client(session)
    a = _assign(session, client_id, PENSIONES_A, T0)
    b = _assign(session, client_id, PENSIONES_B, T0 + timedelta(hours=6))

    judge = _fake_judge({(b.id, a.id): (False, "titulares de hechos distintos")})
    result = reconcile_gray_pairs(
        session, client_id=client_id, now=T0 + timedelta(hours=8), judge=judge
    )
    assert result == {"candidates": 1, "merged": 0, "kept": 1}
    assert session.query(Event).filter(Event.client_id == client_id).count() == 2

    # The memo stops the re-ask: a second pass finds no candidates.
    again = reconcile_gray_pairs(
        session, client_id=client_id, now=T0 + timedelta(hours=9), judge=judge
    )
    assert again == {"candidates": 0}


def test_reconcile_judge_failure_is_conservative(session) -> None:
    """An empty/partial answer merges nothing and records nothing."""
    client_id = _client(session)
    _assign(session, client_id, PENSIONES_A, T0)
    _assign(session, client_id, PENSIONES_B, T0 + timedelta(hours=6))

    result = reconcile_gray_pairs(
        session, client_id=client_id,
        now=T0 + timedelta(hours=8), judge=lambda pairs: {},
    )
    assert result == {"candidates": 1, "merged": 0, "kept": 0}
    assert session.query(EventMerge).count() == 0
    assert session.query(Event).filter(Event.client_id == client_id).count() == 2


def test_merge_events_is_noop_for_missing_source(session) -> None:
    client_id = _client(session)
    a = _assign(session, client_id, PENSIONES_A, T0)
    assert merge_events(session, from_id=99999, to_id=a.id) is False
    assert merge_events(session, from_id=a.id, to_id=a.id) is False


def test_reconcile_without_provider_reports_and_skips(session) -> None:
    """No configured api key -> arbitration off, identity untouched."""
    client_id = _client(session)
    _assign(session, client_id, PENSIONES_A, T0)
    _assign(session, client_id, PENSIONES_B, T0 + timedelta(hours=6))

    result = reconcile_gray_pairs(
        session, client_id=client_id, now=T0 + timedelta(hours=8)
    )
    assert result["candidates"] == 1
    assert result["error"]
    assert session.query(EventMerge).count() == 0
