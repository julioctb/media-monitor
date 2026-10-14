"""Re-align mentions.sentiment/sentiment_score from raw_enrichment.

Canonical policy (app.sentiment.canonical): the LLM enrichment verdict is
the source of truth for sentiment; the local (laya) value only stands
when no enrichment exists. Rows where a stale label/score disagrees with
``raw_enrichment`` are corrected here — batched, idempotent, and safe to
re-run (a second pass changes nothing).

``--dry-run`` (the default) only reports what would change; ``--apply``
writes. ``--client-id`` scopes to one client (default: every client).
Rows whose stored enrichment carries no sentiment, or an unparsable one,
are skipped and counted, never guessed.
"""

import argparse
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Client, Mention
from app.models.base import Sentiment
from app.sentiment.canonical import apply_canonical_sentiment

log = logging.getLogger("align_sentiment")

DEFAULT_BATCH_SIZE = 200


def _canonical_values(mention: Mention) -> tuple[Sentiment, float | None] | None:
    """The (label, score) pair raw_enrichment mandates, if parsable."""
    raw = mention.raw_enrichment
    if not isinstance(raw, dict) or "sentiment" not in raw:
        return None
    try:
        sentiment = Sentiment(raw["sentiment"])
    except ValueError:
        return None
    score = raw.get("sentiment_score")
    return sentiment, float(score) if score is not None else None


def align_sentiment(
    session: Session,
    *,
    client_id: int | None = None,
    apply: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    limit: int | None = None,
) -> dict[str, int]:
    """One idempotent alignment pass; counters per outcome.

    With ``apply`` the canonical value is written batch-size rows at a
    time (one commit per batch); without it nothing is written.
    """
    totals = {"scanned": 0, "would_align": 0, "aligned": 0, "skipped_no_enrichment": 0}
    stmt = select(Mention.id).order_by(Mention.id)
    if client_id is not None:
        stmt = stmt.where(Mention.client_id == client_id)
    if limit is not None:
        stmt = stmt.limit(limit)
    mention_ids = list(session.scalars(stmt))
    changed_in_batch = 0
    for mention_id in mention_ids:
        mention = session.get(Mention, mention_id)
        if mention is None:
            continue
        totals["scanned"] += 1
        canonical = _canonical_values(mention)
        if canonical is None:
            totals["skipped_no_enrichment"] += 1
            continue
        wanted_label, wanted_score = canonical
        changed = apply_canonical_sentiment(
            mention,
            wanted_label,
            wanted_score,
            mention_id=mention.id,
        )
        if changed:
            totals["would_align"] += 1
            if apply:
                totals["aligned"] += 1
                changed_in_batch += 1
                if changed_in_batch >= batch_size:
                    session.commit()
                    changed_in_batch = 0
    if apply and changed_in_batch:
        session.commit()
    return totals


def main() -> None:  # pragma: no cover - CLI wiring
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only (default)")
    mode.add_argument("--apply", action="store_true", help="write the alignment")
    parser.add_argument("--client-id", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=None, help="cap mentions scanned")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        client_ids = (
            list(session.scalars(select(Client.id)))
            if args.client_id is None
            else [args.client_id]
        )
        for client_id in client_ids:
            stats = align_sentiment(
                session,
                client_id=client_id,
                apply=args.apply,
                batch_size=args.batch_size,
                limit=args.limit,
            )
            log.info("client %s align%s: %s", client_id, "/apply" if args.apply else "", stats)
    finally:
        session.close()


if __name__ == "__main__":
    main()
