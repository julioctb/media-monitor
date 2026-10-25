"""Event-identity arbitrator: LLM judgment for the lexical gray band.

Design (odd/tasks/event-identity-llm-arbitrator.md): Jaccard stays the
deterministic floor. This module only sees the pairs it CANNOT settle —
best lexical score strictly between GRAY_MIN and SIMILARITY_THRESHOLD —
and asks a cheap, JSON-strict, temperature-0 model (``ai_model_fast``,
falling back to ``ai_model``) whether the two events are the same story.

Conservative by contract: judge failure or a malformed answer leaves the
pair untouched (and unrecorded, so the next cycle retries); a `distinta`
verdict is recorded as the memo that stops re-asking. Only a `misma`
verdict merges, via :func:`merge_events` — the same primitive the healing
script (T3) uses. Never raises into the ingest cycle: the caller wraps
best-effort, but the module itself commits its own transaction like
``sweep_backlog`` does.
"""

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.enrich.llm import ATTEMPTS, DEFAULT_OPENAI_MODEL, LLMEnricher
from app.ingest.events import (
    SIMILARITY_THRESHOLD,
    WINDOW_HOURS,
    Event,
    _event_best_score,
    _tokens,
    event_title_pool,
)
from app.models import EventMerge, Mention
from app.settings_runtime import resolve_effective_settings

#: Band edges (initial; calibrated with scripts/near_dupes_sweep.py —
#: measured production grays: pensiones 0.364, finanzas-parking 0.214).
GRAY_MIN = 0.30
#: Hard cap of pairs judged per cycle (open point 4 of the design doc).
PAIR_CAP = 10
#: Distinct from enrich (20s) and digest (60s): tiny calls, short leash.
TIMEOUT_S = 10.0

Judge = Callable[["list[GrayPair]"], "dict[tuple[int, int], PairVerdict]"]


@dataclass(frozen=True)
class GrayPair:
    from_id: int
    to_id: int
    score: float
    title_a: str
    title_b: str


class PairVerdict(BaseModel):
    model_config = ConfigDict(extra="ignore")

    a: int
    b: int
    mismo: bool
    razon: str = ""


class JudgeResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    pares: list[PairVerdict] = []


ARBITER_SYSTEM_PROMPT = (
    "Eres el árbitro de identidad de historias de un sistema de monitoreo "
    "de medios. Decides si dos titulares cubren LA MISMA historia noticiosa "
    "(mismos hechos, protagonistas y suceso) o historias distintas. Ángulos "
    "o desarrollos diferentes del mismo tema general son historias "
    "distintas. Criterio conservador: ante duda razonable, responde que "
    "son distintas. Respondes SOLO con JSON con la forma "
    '{"pares": [{"a": <id>, "b": <id>, "mismo": true|false, '
    '"razon": "máximo 15 palabras"}]}.'
)


def _pair_score(
    a: Event, b: Event, pools: dict[int, list[str]]
) -> float:
    """Symmetric best lexical score between two events (canonical + pools)."""
    return max(
        _event_best_score(a.title, b, pools.get(b.id, [])),
        _event_best_score(b.title, a, pools.get(a.id, [])),
    )


def adjudicated_pairs(session: Session, client_id: int) -> set[frozenset[int]]:
    """Unordered id pairs already judged — the do-not-re-ask memo."""
    rows = session.execute(
        select(EventMerge.event_from, EventMerge.event_to).where(
            EventMerge.client_id == client_id
        )
    ).all()
    return {frozenset((int(f), int(t))) for f, t in rows}


def find_gray_pairs(
    session: Session,
    *,
    client_id: int,
    now: datetime | None = None,
    window_hours: int = WINDOW_HOURS,
    cap: int = PAIR_CAP,
) -> list[GrayPair]:
    """Live events of the client whose best cross-score falls in the band.

    Anchor convention: the event with more mentions survives a merge
    (ties: the lower id) — `from_id` is the one that would disappear.
    """
    now = now or datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=window_hours)
    events = [
        e
        for e in session.scalars(
            select(Event)
            .where(
                Event.client_id == client_id,
                Event.last_seen_at >= cutoff,
            )
            .order_by(Event.id)
        )
        if e.mention_count > 0
    ]
    pools = event_title_pool(session, events)
    seen = adjudicated_pairs(session, client_id)
    pairs: list[GrayPair] = []
    for i, a in enumerate(events):
        for b in events[i + 1 :]:
            if frozenset((a.id, b.id)) in seen:
                continue
            score = _pair_score(a, b, pools)
            if not (GRAY_MIN < score < SIMILARITY_THRESHOLD):
                continue
            # Anchor = the event that survives; from = the one that goes.
            if (b.mention_count, -b.id) > (a.mention_count, -a.id):
                anchor, going = b, a
            else:
                anchor, going = a, b
            pairs.append(
                GrayPair(
                    from_id=going.id,
                    to_id=anchor.id,
                    score=score,
                    title_a=a.title,
                    title_b=b.title,
                )
            )
    pairs.sort(key=lambda p: -p.score)
    return pairs[:cap]


def merge_events(session: Session, *, from_id: int, to_id: int) -> bool:
    """Fold `from_id` into `to_id`: reassign mentions, re-anchor, delete.

    Idempotent-by-absence: a missing or already-merged `from_id` is a no-op
    returning False. Caller records the audit row (reconcile/healing own
    the EventMerge write so verdict context stays with the judgment).
    """
    from_event = session.get(Event, from_id)
    to_event = session.get(Event, to_id)
    if from_event is None or to_event is None or from_event.id == to_event.id:
        return False

    session.execute(
        update(Mention).where(Mention.event_id == from_id).values(event_id=to_id)
    )
    session.flush()

    mentions = list(
        session.scalars(
            select(Mention).where(Mention.event_id == to_id)
        )
    )
    to_event.mention_count = len(mentions)
    to_event.source_count = len({m.source for m in mentions})
    to_event.first_seen_at = min(to_event.first_seen_at, from_event.first_seen_at)
    to_event.last_seen_at = max(to_event.last_seen_at, from_event.last_seen_at)
    if len(from_event.title) > len(to_event.title):
        to_event.title = from_event.title
    to_event.title_tokens = " ".join(sorted(_tokens(to_event.title)))

    session.delete(from_event)
    session.flush()
    return True


def build_default_judge(session: Session, *, client_id: int) -> Judge | None:
    """Judge backed by the configured provider on the fast model.

    None (no arbitration) when no api_key is configured — the ingest cycle
    must keep running exactly as before in that case.
    """
    effective = resolve_effective_settings(session, client_id)
    if not effective.ai_api_key:
        return None
    enricher = LLMEnricher(
        api_key=effective.ai_api_key,
        base_url=effective.ai_base_url,
        model=effective.fast_model or DEFAULT_OPENAI_MODEL,
        timeout=TIMEOUT_S,
        attempts=ATTEMPTS,
    )

    def judge(pairs: list[GrayPair]) -> dict[tuple[int, int], PairVerdict]:
        user = json.dumps(
            {
                "pares": [
                    {
                        "a": p.from_id,
                        "b": p.to_id,
                        "titulo_a": p.title_a[:200],
                        "titulo_b": p.title_b[:200],
                    }
                    for p in pairs
                ]
            },
            ensure_ascii=False,
        )
        raw = enricher.ask_json(ARBITER_SYSTEM_PROMPT, user)
        if not raw:
            return {}
        try:
            parsed = JudgeResponse.model_validate_json(raw)
        except ValueError:
            return {}
        return {
            (int(v.a), int(v.b)): v
            for v in parsed.pares
            if isinstance(v.mismo, bool)
        }

    judge.model = enricher.model_name  # type: ignore[attr-defined]
    return judge


def reconcile_gray_pairs(
    session: Session,
    *,
    client_id: int,
    now: datetime | None = None,
    judge: Judge | None = None,
) -> dict[str, int | str]:
    """One arbitration pass: detect grays, judge, merge/record.

    Returns counts for the worker log (``candidates`` only when idle).
    Judge entries missing from the answer stay unrecorded — a half-answer
    retries next cycle instead of freezing a wrong identity.
    """
    pairs = find_gray_pairs(session, client_id=client_id, now=now)
    if not pairs:
        return {"candidates": 0}
    if judge is None:
        judge = build_default_judge(session, client_id=client_id)
        if judge is None:
            return {"candidates": len(pairs), "error": "sin proveedor configurado"}

    verdicts = judge(pairs)
    merged = kept = 0
    for pair in pairs:
        verdict = verdicts.get((pair.from_id, pair.to_id))
        if verdict is None:
            continue
        if verdict.mismo and merge_events(
            session, from_id=pair.from_id, to_id=pair.to_id
        ):
            merged += 1
        else:
            kept += 1
        session.add(
            EventMerge(
                client_id=client_id,
                event_from=pair.from_id,
                event_to=pair.to_id,
                score=pair.score,
                verdict="misma" if verdict.mismo else "distinta",
                reason=(verdict.razon or "")[:300],
                model=getattr(judge, "model", None),
            )
        )
    session.commit()
    return {"candidates": len(pairs), "merged": merged, "kept": kept}
