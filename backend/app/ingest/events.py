"""Canonical event clustering: token-Jaccard similarity inside a 48h window.

Deterministic, in-process, no embeddings (per plan Fase 2): a mention joins
the most similar open event of its client, else a new event is created.
The event's aggregates (counts, seen-window, canonical title) are recomputed
on every assignment via :func:`touch_event`.
"""

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingest.matching import fold_text
from app.models import Event, Mention

WINDOW_HOURS = 48
SIMILARITY_THRESHOLD = 0.5
STOPWORDS = frozenset(
    "de en la por a el y del los las un una con para al su sus".split()
)

_TOKEN_RE = re.compile(r"\w+")


def _stem(token: str) -> str:
    """Light Spanish stem: keep the first 6 chars.

    Fuses the frequent inflections that would otherwise split one story's
    token in two (inaugura/inaugurado, Zacapoaxtla typo variants) without
    pulling a real stemmer into the ingest path.
    """
    return token[:6]


def _tokens(title: str) -> set[str]:
    """Folded content stems: accents/case folded, stopwords and short
    fragments dropped so 'BUAP'/'buap'/'la' never steer the similarity."""
    return {
        _stem(token)
        for token in _TOKEN_RE.findall(fold_text(title))
        if len(token) > 2 and token not in STOPWORDS
    }


def similarity(a: str, b: str) -> float:
    """Jaccard of the folded token sets; 0.0 when either side is empty."""
    tokens_a, tokens_b = _tokens(a), _tokens(b)
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    if not intersection:
        return 0.0
    return intersection / len(tokens_a | tokens_b)


def _aware(dt: datetime) -> datetime:
    """UTC-normalize for comparisons: SQLite roundtrips naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def touch_event(event: Event, mention: Mention) -> None:
    """Recompute the event aggregates once `mention` is linked to it.

    Counts derive from the linked mentions (not increments) so the
    recomputation is idempotent: backfills and re-assignments converge to
    the same totals. The seen-window stretches to cover the mention and the
    canonical title becomes the longest seen (plan: longest title wins).
    """
    event.mention_count = len(event.mentions)
    event.source_count = len({m.source for m in event.mentions})
    when = _aware(mention.published_at) if mention.published_at is not None else None
    if when is not None:
        first = _aware(event.first_seen_at) if event.first_seen_at else None
        last = _aware(event.last_seen_at) if event.last_seen_at else None
        if first is None or when < first:
            event.first_seen_at = when
        if last is None or when > last:
            event.last_seen_at = when
    if mention.title and len(mention.title) > len(event.title):
        event.title = mention.title
    event.title_tokens = " ".join(sorted(_tokens(event.title)))


def find_or_create_event(
    session: Session, *, client_id: int, title: str, when: datetime
) -> Event:
    """Assign `title` to the best event of the client inside the window.

    Candidates: same client with first/last_seen within +/- 48h of `when`.
    Ranked by token-Jaccard against the canonical title, ties broken by id
    (deterministic). Below threshold (or no candidates) a new event is
    created. Does not commit; the caller owns the transaction.
    """
    window_start = when - timedelta(hours=WINDOW_HOURS)
    window_end = when + timedelta(hours=WINDOW_HOURS)
    candidates = list(
        session.scalars(
            select(Event).where(
                Event.client_id == client_id,
                Event.first_seen_at <= window_end,
                Event.last_seen_at >= window_start,
            )
        )
    )
    best: Event | None = None
    best_score = 0.0
    for event in sorted(candidates, key=lambda e: e.id):
        score = similarity(title, event.title)
        if score > best_score:
            best, best_score = event, score
    if best is not None and best_score >= SIMILARITY_THRESHOLD:
        event = best
    else:
        event = Event(
            client_id=client_id,
            title=title,
            title_tokens=" ".join(sorted(_tokens(title))),
            first_seen_at=when,
            last_seen_at=when,
        )
        session.add(event)
        session.flush()
    return event


def assign_mention_to_event(session: Session, mention: Mention) -> None:
    """Find-or-create the event for `mention` and link + recount it.

    Mentions without a title carry no event (NULL event_id). No commit:
    the caller owns the transaction, as everywhere in the pipeline.
    """
    if not mention.title:
        return
    when = mention.published_at or mention.ingested_at
    event = find_or_create_event(
        session,
        client_id=mention.client_id,
        title=mention.title,
        when=when,
    )
    mention.event_id = event.id
    mention.event = event
    touch_event(event, mention)
