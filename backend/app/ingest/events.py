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
from app.models.base import MentionSource

WINDOW_HOURS = 48
SIMILARITY_THRESHOLD = 0.5
#: Media sources carry editorial headlines; social/field do not. The event
#: canonical prefers media titles (D2): a longer social mega-title must not
#: become the face of a story (the «Feliz viernes» portada case).
MEDIA_EVENT_SOURCES = frozenset(
    {
        MentionSource.news_rss,
        MentionSource.gdelt,
        MentionSource.rss_custom,
        MentionSource.scraper,
    }
)
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


_OUTLET_SUFFIX_RE = re.compile(r"\s+-\s+[^-]+$")

#: Front-page showcase posts (portadas) quote a whole front page: their
#: title carries SEVERAL stories' headlines. They are a showcase, not a
#: story — quarantined from event identity (D1, digest-coherence 25/oct:
#: one such post bridged presupuesto+pensiones into a single mega-event).
_AGGREGATE_TITLE_RE = re.compile(
    r"(esta es la portada|portada de @|portada de hoy|portada del d[ií]a)",
    re.IGNORECASE,
)


def is_aggregate_title(title: str | None) -> bool:
    """True for front-page showcase titles that aggregate several stories."""
    return bool(title and _AGGREGATE_TITLE_RE.search(title))


def strip_outlet_suffix(title: str) -> str:
    """Drop a dash-introduced outlet signature, including its pipe sections.

    A pipe alone is ambiguous: ``Institution | Opens library`` contains
    substantive story text, not an outlet suffix. Preserve that content.
    Repeated dash signatures such as ``story - Outlet | Section`` still
    reduce to the headline; raw publication titles are never rewritten.
    """
    out = title.strip()
    while True:
        stripped = _OUTLET_SUFFIX_RE.sub("", out).strip()
        if stripped == out or not stripped:
            return out
        out = stripped


def similarity_with_suffix_variants(a: str, b: str) -> float:
    """Best of the plain and the suffix-stripped comparison.

    Never below :func:`similarity`; strictly higher when outlet suffixes
    were diluting the token overlap (measured: 132 lost merges / 15d).
    """
    return max(
        similarity(a, b),
        similarity(strip_outlet_suffix(a), strip_outlet_suffix(b)),
    )


def _aware(dt: datetime) -> datetime:
    """UTC-normalize for comparisons: SQLite roundtrips naive datetimes."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def recompute_canonical(event: Event) -> None:
    """D2: canonical = longest MEDIA headline; social only with no media;
    aggregate showcase titles never. Recomputed from linked mentions, so
    backfills and merges converge (idempotent like the counters)."""
    titles = [
        m.title for m in event.mentions if m.title and not is_aggregate_title(m.title)
    ]
    media_titles = [
        m.title
        for m in event.mentions
        if m.title
        and not is_aggregate_title(m.title)
        and m.source in MEDIA_EVENT_SOURCES
    ]
    best = max(media_titles or titles, key=len, default=None)
    if best is not None:
        event.title = best
    event.title_tokens = " ".join(sorted(_tokens(event.title)))


def touch_event(event: Event, mention: Mention) -> None:
    """Recompute the event aggregates once `mention` is linked to it.

    Counts derive from the linked mentions (not increments) so the
    recomputation is idempotent: backfills and re-assignments converge to
    the same totals. The seen-window stretches to cover the mention. The
    canonical title (D2) is the longest MEDIA headline among the grouped
    mentions — social titles only when no media headline exists, and
    aggregate showcase titles never (D1).
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
    recompute_canonical(event)


#: T1 (event-identity): the assigner scores the incoming title against the
#: canonical AND the distinct titles the event has already grouped (capped).
#: The canonical alone drifts — `touch_event` keeps the longest title — and
#: measured splits (finanzas 23-24: 0.636 on stored titles) were lost because
#: the assignment-time comparison used a different string than today's.
EVENT_TITLE_POOL_CAP = 10


def event_title_pool(session: Session, events: list[Event]) -> dict[int, list[str]]:
    """Distinct mention titles per event (longest first, capped).

    The drift-proof comparison pool: a new headline matching ANY wording the
    event already grouped scores against it, not just against the canonical.
    """
    ids = [e.id for e in events]
    if not ids:
        return {}
    rows = session.execute(
        select(Mention.event_id, Mention.title).where(
            Mention.event_id.in_(ids), Mention.title.is_not(None)
        )
    ).all()
    pool: dict[int, set[str]] = {}
    for event_id, title in rows:
        if title and not is_aggregate_title(title):
            pool.setdefault(event_id, set()).add(title)
    return {
        event_id: sorted(titles, key=len, reverse=True)[:EVENT_TITLE_POOL_CAP]
        for event_id, titles in pool.items()
    }


def _event_best_score(title: str, event: Event, pool: list[str]) -> float:
    """Best score against non-aggregate canonical and historical titles."""
    if is_aggregate_title(title):
        return 0.0
    score = (
        0.0
        if is_aggregate_title(event.title)
        else similarity_with_suffix_variants(title, event.title)
    )
    for alt in pool:
        if alt == event.title or is_aggregate_title(alt):
            continue
        alt_score = similarity_with_suffix_variants(title, alt)
        if alt_score > score:
            score = alt_score
    return score


def find_or_create_event(
    session: Session, *, client_id: int, title: str, when: datetime
) -> Event:
    """Assign `title` to the best event of the client inside the window.

    Candidates: same client with first/last_seen within +/- 48h of `when`.
    Ranked by token-Jaccard against the canonical title and the event's
    title pool (best of the plain and suffix-stripped variants), ties
    broken by id (deterministic). Below threshold (or no candidates) a new
    event is created. Does not commit; the caller owns the transaction.
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
    pools = event_title_pool(session, candidates)
    best: Event | None = None
    best_score = 0.0
    for event in sorted(candidates, key=lambda e: e.id):
        score = _event_best_score(title, event, pools.get(event.id, []))
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

    Mentions without a title carry no event (NULL event_id), and so do
    aggregate showcase titles (D1: portadas bridge stories and hijack
    canonicals — they are coverage, not identity). No commit: the caller
    owns the transaction, as everywhere in the pipeline.
    """
    if not mention.title or is_aggregate_title(mention.title):
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
