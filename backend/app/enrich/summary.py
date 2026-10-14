"""Event-level summary synthesis (F2c TE3).

The event summary is the primary RAG chunk and the digest line, so it is
kept in ``events.summary`` and refreshed on every new mention:

  - 1 mention          -> the canonical title IS the summary (no LLM call)
  - 2+ mentions        -> one LLM pass over the mention summaries (never
                          raw content: cheap), falling back to nothing on
                          failure so a previous good summary survives

Every failure is contained: the event row just keeps its previous value.
"""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Event, Mention

log = logging.getLogger("enrich.summary")

#: Upper bound on mention summaries handed to the synthesizer.
MAX_INPUTS = 20


def _mention_inputs(session: Session, event_id: int) -> list[str]:
    """Enrichment summaries when present, titles otherwise; non-empty."""
    rows = session.execute(
        select(Mention.summary, Mention.title).where(Mention.event_id == event_id)
    ).all()
    inputs = [(summary or title or "").strip() for summary, title in rows]
    return [text for text in inputs if text][:MAX_INPUTS]


def maybe_summarize_event(
    session: Session, event: Event, *, enricher
) -> str | None:
    """Refresh ``event.summary``; returns the stored value, None if untouched.

    Caller owns enrichment-failure isolation only for the LLM path — the
    single-mention branch is deterministic. The write commits on success.
    """
    inputs = _mention_inputs(session, event.id)
    if not inputs:
        return None
    if len(inputs) == 1:
        summary: str | None = event.title.strip()
    else:
        summary = (enricher.summarize(inputs) or "").strip() or None
        if summary is None:
            return None  # keep any previous summary; backfillable later
    if summary == event.summary:
        return event.summary
    event.summary = summary
    session.commit()
    log.debug("event %s summary refreshed (%d inputs)", event.id, len(inputs))
    return summary
