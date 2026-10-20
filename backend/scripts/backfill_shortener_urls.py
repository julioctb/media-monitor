"""One-off: resolve shortener URLs (t.co...) to the publisher URL.

Run inside the api/worker container::

    python -m scripts.backfill_shortener_urls

Keeps ``url_hash`` untouched (dedupe already happened at insert); only
``url`` is rewritten so the UI shows the real outlet.
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.ingest.article_fetch import _is_shortener, resolve_publisher_url
from app.models import Mention


def main() -> None:
    session = SessionLocal()
    updated = 0
    skipped = 0
    try:
        rows = session.scalars(select(Mention).where(Mention.url.is_not(None)))
        for mention in rows:
            if not _is_shortener(mention.url):
                continue
            resolved = resolve_publisher_url(mention.url)
            if resolved and resolved != mention.url:
                mention.url = resolved
                updated += 1
            else:
                skipped += 1
        session.commit()
        print(f"backfill shortener urls: updated={updated} unresolved={skipped}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
