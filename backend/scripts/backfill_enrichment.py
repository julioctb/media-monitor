"""Backfill LLM enrichment for mentions (F2c TE4).

Rows with ``summary NULL`` are the backlog (enrichment failures and
mentions ingested before the feature). ``--dry-run`` (the default) only
reports the candidate count and the projected token/cost spend — no LLM
call happens; ``--apply`` runs the enrichment through the client's
configured ``ai_provider`` exactly like the ingest cycle does, filling
summary, sentiment (canonical: overwrites any earlier value, the
previous one is logged) and topics. ``--force`` re-enriches rows that
already carry a summary.

Cost model: the input side is estimated per row from the truncated
article length (~4 chars/token) plus prompt overhead; output is the plan
constant (~300 tokens/mention). Prices are USD per million tokens,
overridable via ``--price-in`` / ``--price-out``; the defaults mirror
gpt-4o-mini. The estimate exists to size the spend BEFORE any call.
"""

import argparse
import logging
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.enrich.llm import ESTIMATED_OUTPUT_TOKENS, MAX_CONTENT_CHARS
from app.models import Client, Mention, MentionPerson, queries
from app.sentiment.canonical import apply_canonical_sentiment
from sqlalchemy import select
from sqlalchemy.orm import Session

log = logging.getLogger("backfill.enrichment")

#: Prompt + response-envelope overhead per enrichment call, on top of
#: the article tokens (system prompt ~250 tokens, round up).
PROMPT_OVERHEAD_TOKENS = 300

#: ~4 characters per token for Spanish news text (conservative).
CHARS_PER_TOKEN = 4

DEFAULT_PRICE_PER_M_IN = 0.15
DEFAULT_PRICE_PER_M_OUT = 0.60


def _text_of(mention: Mention) -> str:
    parts = [mention.title or "", mention.content or ""]
    return "\n".join(part for part in parts if part)


def estimate_input_tokens(text: str) -> int:
    """Token estimate for one enrichment call (article + prompt overhead)."""
    clipped = min(len(" ".join(text.split())), MAX_CONTENT_CHARS)
    return (clipped // CHARS_PER_TOKEN) + PROMPT_OVERHEAD_TOKENS


def load_ids_file(path: str) -> list[int]:
    """One mention id per line; blank lines and #comments ignored."""
    ids: list[int] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            stripped = line.split("#", 1)[0].strip()
            if stripped:
                ids.append(int(stripped))
    return ids


def candidate_ids(
    session: Session,
    *,
    client_id: int | None = None,
    force: bool = False,
    since: datetime | None = None,
    before: datetime | None = None,
    ids: list[int] | None = None,
    with_persons: bool = False,
) -> list[int]:
    """Mentions needing enrichment: summary NULL, or every row with force.

    ``ids`` (from --ids-file) pins the candidate set to exactly those rows
    (still intersected with client/since filters). ``with_persons`` keeps
    only rows with at least one person link — the re-enrichment scope when
    the goal is repairing the persons graph without touching the rest.
    ``before`` bounds ingested_at from above (sweep: only rows older than
    the ingest window, which owns fresh rows).
    """
    stmt = select(Mention.id).order_by(Mention.id)
    if not force:
        stmt = stmt.where(Mention.summary.is_(None))
    if ids is not None:
        stmt = stmt.where(Mention.id.in_(ids))
    if client_id is not None:
        stmt = stmt.where(Mention.client_id == client_id)
    if since is not None:
        stmt = stmt.where(Mention.ingested_at >= since)
    if before is not None:
        stmt = stmt.where(Mention.ingested_at < before)
    if with_persons:
        stmt = stmt.where(
            Mention.id.in_(select(MentionPerson.mention_id).distinct())
        )
    return list(session.scalars(stmt))


def project_cost(
    session: Session,
    mention_ids: list[int],
    *,
    price_in: float = DEFAULT_PRICE_PER_M_IN,
    price_out: float = DEFAULT_PRICE_PER_M_OUT,
) -> dict[str, float | int]:
    """Token/cost projection over the given rows; no LLM call."""
    rows = session.execute(
        select(Mention.id, Mention.title, Mention.content).where(
            Mention.id.in_(mention_ids)
        )
    ).all()
    in_tokens = sum(
        estimate_input_tokens(_text_of(Mention(id=id_, title=title, content=content)))
        for id_, title, content in rows
    )
    out_tokens = ESTIMATED_OUTPUT_TOKENS * len(rows)
    cost = in_tokens / 1e6 * price_in + out_tokens / 1e6 * price_out
    return {
        "mentions": len(rows),
        "input_tokens": in_tokens,
        "output_tokens_est": out_tokens,
        "cost_usd_est": round(cost, 4),
    }


def backfill(
    session: Session,
    enricher,
    *,
    client_id: int | None = None,
    force: bool = False,
    limit: int | None = None,
    batch_size: int = 50,
    ids: list[int] | None = None,
    with_persons: bool = False,
) -> dict[str, int]:
    """Enrich candidate mentions; counters per outcome.

    Enrichment failure leaves the row untouched (still backfillable);
    sentiment is canonical (app.sentiment.canonical): the enrichment
    verdict overwrites any stored value, and the previous label/score is
    logged when it differs (``canonical_overrides`` counts those rows).
    """
    ids = candidate_ids(
        session, client_id=client_id, force=force, ids=ids, with_persons=with_persons
    )
    if limit is not None:
        ids = ids[:limit]
    totals = {
        "enriched": 0,
        "failed": 0,
        "skipped_empty": 0,
        "canonical_overrides": 0,
        "persons_relinked": 0,
        "candidates": len(ids),
    }
    processed = 0
    for mention_id in ids:
        mention = session.get(Mention, mention_id)
        if mention is None:
            continue
        text = _text_of(mention)
        if not text.strip():
            totals["skipped_empty"] += 1
            continue
        try:
            result = enricher.enrich(text, lang=mention.lang or "es")
        except Exception as exc:  # noqa: BLE001 - one row must not stop the run
            log.warning("enrichment backfill failed for %s: %s", mention_id, exc)
            totals["failed"] += 1
            continue
        if result is None:
            totals["failed"] += 1
            continue
        mention.summary = result.summary
        # F3 read-back: same payload the ingest path stores.
        mention.raw_enrichment = result.model_dump(mode="json")
        # Re-link persons from the fresh payload: existing links reflect the
        # previous extraction and would survive a prompt/policy change.
        # Savepoint-scoped so one bad relink never drops the batch.
        try:
            with session.begin_nested():
                session.query(MentionPerson).filter(  # type: ignore[attr-defined]
                    MentionPerson.mention_id == mention.id
                ).delete(synchronize_session=False)
                from app.persons import persist_persons_from_enrichment

                persist_persons_from_enrichment(session, mention)
            totals["persons_relinked"] += 1
        except Exception as exc:  # noqa: BLE001 - relink must not block backfill
            log.warning("persons relink failed for %s: %s, keeping previous links", mention.id, exc)
        # Classification v2: the enrichment topic is canonical — the same
        # upsert the ingest path runs for enriched mentions.
        if result.topic:
            try:
                queries.upsert_classifications(
                    session,
                    mention_id=mention.id,
                    classifier="topic",
                    results=[(result.topic, 1.0)],
                )
            except Exception as exc:  # noqa: BLE001 - topics must not block
                log.warning("canonical topic backfill failed for %s: %s", mention.id, exc)
        # Canonical policy: the enrichment verdict overwrites any earlier
        # analyzer value; the previous label/score lands in the log.
        if apply_canonical_sentiment(
            mention,
            result.sentiment,
            result.sentiment_score,
            mention_id=mention.id,
        ):
            totals["canonical_overrides"] += 1
        if result.topics:
            try:
                queries.upsert_classifications(
                    session,
                    mention_id=mention.id,
                    classifier="topics",
                    results=[(topic, 1.0) for topic in result.topics],
                )
            except Exception as exc:  # noqa: BLE001 - topics must not block
                log.warning("topics backfill failed for %s: %s", mention.id, exc)
        totals["enriched"] += 1
        processed += 1
        if processed % batch_size == 0:
            session.commit()
    if processed:
        session.commit()
    return totals


def build_enricher_from_settings(session: Session, client_id: int):
    """The same construction path the ingest cycle uses; None if unusable."""
    from app.settings_runtime import load_cycle_settings

    load_cycle_settings(session, client_id=client_id)
    from app.worker import cycle_enricher

    enricher, _ = cycle_enricher(client_id)
    return enricher


#: Worker sweep defaults: rows per cycle and minimum age before the sweep
#: touches a row (the ingest cycle owns fresh mentions and their cap).
SWEEP_LIMIT = 25
SWEEP_MIN_AGE_H = 2


def sweep_backlog(
    session: Session,
    enricher,
    *,
    client_id: int,
    now: datetime,
    limit: int = SWEEP_LIMIT,
    min_age_h: int = SWEEP_MIN_AGE_H,
) -> dict[str, int]:
    """Self-heal pass: re-enrich the stale unclassified backlog.

    Picks the OLDEST summary-NULL mentions older than ``min_age_h`` —
    rows the ingest cycle's per-cycle cap, a provider outage or a
    settings window left behind — and runs the normal ``backfill`` on
    them (canonical sentiment, persons relink, classifications). Called
    once per ingest cycle by the worker; failures leave rows touchable
    again next cycle, so the backlog drains without manual backfills.
    """
    cutoff = now - timedelta(hours=min_age_h)
    stale = candidate_ids(session, client_id=client_id, before=cutoff)
    if not stale:
        return {
            "enriched": 0,
            "failed": 0,
            "skipped_empty": 0,
            "canonical_overrides": 0,
            "persons_relinked": 0,
            "candidates": 0,
        }
    return backfill(session, enricher, client_id=client_id, ids=stale[:limit])


def main() -> None:  # pragma: no cover - CLI wiring
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="estimate only (default)")
    mode.add_argument("--apply", action="store_true", help="run the enrichment")
    parser.add_argument("--client-id", type=int, default=None)
    parser.add_argument("--force", action="store_true", help="re-enrich enriched rows")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument(
        "--hours", type=float, default=None,
        help="restrict to mentions ingested in the last N hours",
    )
    parser.add_argument(
        "--ids-file", default=None,
        help="file with one mention id per line; only those rows are candidates",
    )
    parser.add_argument(
        "--with-persons", action="store_true",
        help="only mentions with at least one person link (persons repair)",
    )
    parser.add_argument(
        "--price-in", type=float, default=DEFAULT_PRICE_PER_M_IN,
        help="USD per million input tokens",
    )
    parser.add_argument(
        "--price-out", type=float, default=DEFAULT_PRICE_PER_M_OUT,
        help="USD per million output tokens",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        if args.client_id is None:
            client_ids = list(session.scalars(select(Client.id)))
        else:
            client_ids = [args.client_id]
        for client_id in client_ids:
            since = (
                datetime.now(tz=UTC) - timedelta(hours=args.hours)
                if args.hours is not None
                else None
            )
            pinned_ids = load_ids_file(args.ids_file) if args.ids_file else None
            ids = candidate_ids(
                session, client_id=client_id, force=args.force, since=since,
                ids=pinned_ids, with_persons=args.with_persons,
            )
            if args.limit is not None:
                ids = ids[: args.limit]
            projection = project_cost(session, ids, price_in=args.price_in, price_out=args.price_out)
            log.info("client %s projection: %s", client_id, projection)
            if not args.apply:
                continue
            if not ids:
                log.info("client %s: no candidates; skipping", client_id)
                continue
            enricher = build_enricher_from_settings(session, client_id)
            if enricher is None:
                log.warning("client %s: no usable ai_provider; skipping", client_id)
                continue
            with enricher:
                stats = backfill(
                    session,
                    enricher,
                    client_id=client_id,
                    force=args.force,
                    limit=args.limit,
                    ids=pinned_ids,
                    with_persons=args.with_persons,
                )
                log.info("client %s backfill: %s", client_id, stats)
    finally:
        session.close()


if __name__ == "__main__":
    main()
