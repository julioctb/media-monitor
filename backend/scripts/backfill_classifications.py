"""Full re-classification of mentions with one registry classifier.

Deletes every row of the classifier for the client's mentions, then
re-runs the model over all of them (sentiment columns untouched).
Host-runnable against any DATABASE_URL:

    DATABASE_URL=postgresql+psycopg://... python -m scripts.backfill_classifications \
        --classifier political

The classifier and the Laya agent are built lazily: importing this module
never loads a model.
"""

import argparse
import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Client, Mention, MentionClassification, queries

log = logging.getLogger("backfill.classifications")


def _text_of(mention: Mention) -> str:
    parts = [mention.title or "", mention.content or ""]
    return "\n".join(part for part in parts if part)


def reclassify(
    session: Session,
    classifier,
    *,
    client_ids: list[int] | None = None,
    batch_size: int = 200,
    limit: int | None = None,
) -> dict[str, int]:
    """Wipe the classifier's rows, reclassify, return counters.

    Per client: one bulk delete of this classifier's rows followed by a
    full pass over the mentions (id-stable pagination, commits per batch).
    A per-mention failure just leaves the row absent for a later retry.
    """
    totals = {"deleted": 0, "classified": 0, "skipped_empty": 0, "failed": 0}
    ids = client_ids if client_ids is not None else list(session.scalars(select(Client.id)))
    for client_id in ids:
        result = session.execute(
            delete(MentionClassification).where(
                MentionClassification.classifier == classifier.name,
                MentionClassification.mention_id.in_(
                    select(Mention.id).where(Mention.client_id == client_id)
                ),
            )
        )
        session.commit()
        totals["deleted"] += int(result.rowcount or 0)
        log.info(
            "client %s: deleted %d rows for classifier %s",
            client_id,
            result.rowcount or 0,
            classifier.name,
        )

        processed = 0
        offset = 0
        while True:
            batch = queries.list_mentions(
                session, client_id, limit=batch_size, offset=offset
            )
            if not batch:
                break
            offset += len(batch)
            for mention in batch:
                if limit is not None and processed >= limit:
                    break
                text = _text_of(mention)
                if not text.strip():
                    totals["skipped_empty"] += 1
                    continue
                try:
                    prediction = classifier.classify(text, lang=mention.lang or "es")
                except Exception as exc:  # noqa: BLE001 - one row must not stop the run
                    log.warning(
                        "classification failed for mention %s: %s", mention.id, exc
                    )
                    totals["failed"] += 1
                    continue
                queries.upsert_classification(
                    session,
                    mention_id=mention.id,
                    classifier=classifier.name,
                    label=prediction.label,
                    score=prediction.score,
                )
                totals["classified"] += 1
                processed += 1
                if processed % batch_size == 0:
                    session.commit()
            if limit is not None and processed >= limit:
                break
        if processed % batch_size:
            session.commit()
    return totals


def build_classifier(name: str):
    """Registry-backed factory; validates the name before any model loads."""
    from app.classifications import build_classifiers

    return build_classifiers([name])[0]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    from app.classifications import classifier_names

    parser.add_argument(
        "--classifier",
        default=classifier_names()[0] if classifier_names() else None,
        choices=classifier_names(),
        help="registry classifier to (re)run",
    )
    parser.add_argument("--client-id", type=int, action="append", help="limit to these clients")
    parser.add_argument("--limit", type=int, default=None, help="max mentions to classify")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    session = SessionLocal()
    try:
        classifier = build_classifier(args.classifier)
        totals = reclassify(
            session,
            classifier,
            client_ids=args.client_id,
            batch_size=args.batch_size,
            limit=args.limit,
        )
        log.info("classification backfill complete: %s", totals)
        for client_row in session.scalars(select(Client.id)):
            breakdown = queries.classification_breakdown(
                session, client_id=client_row, classifier=args.classifier
            )
            log.info(
                "client %s breakdown for %s: %s",
                client_row,
                args.classifier,
                breakdown,
            )
    finally:
        session.close()


if __name__ == "__main__":
    main()
