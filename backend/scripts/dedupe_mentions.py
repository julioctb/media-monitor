"""One-shot: collapse cross-URL duplicate mentions (same client+source+title).

Run from repo root against the target DB, e.g.:
    DATABASE_URL=postgresql+psycopg://media:media@localhost:5432/mediamonitor \
        PYTHONPATH=backend .venv/bin/python backend/scripts/dedupe_mentions.py
"""

import logging

from app.db import SessionLocal
from app.models.queries import dedupe_duplicate_titles


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    session = SessionLocal()
    try:
        removed = dedupe_duplicate_titles(session)
        logging.info("dedupe complete: removed %d duplicate mention(s)", removed)
    finally:
        session.close()


if __name__ == "__main__":
    main()
