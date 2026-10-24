"""One-off: resolve Google News redirect URLs to the publisher URL.

Run inside the api/worker container::

    python -m scripts.backfill_google_news_urls

Historical rows ingested before the article_fetch resolver ran keep
``news.google.com/rss/articles/...`` links, which hide the real outlet from
the medium facet. Keeps ``url_hash`` untouched (dedupe already happened at
insert); only ``url`` is rewritten. Commits in batches; safe to re-run.
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.ingest.article_fetch import _is_google_news, resolve_publisher_url
from app.models import Mention

BATCH = 50


def main() -> None:
    import httpx

    session = SessionLocal()
    updated = 0
    unresolved = 0
    seen = 0
    try:
        rows = session.scalars(
            select(Mention).where(Mention.url.is_not(None), Mention.url.like("%news.google.com%"))
        )
        with httpx.Client(timeout=15, follow_redirects=True) as client:
            for mention in rows:
                seen += 1
                if not _is_google_news(mention.url):
                    continue
                resolved = resolve_publisher_url(mention.url, client)
                if resolved and resolved != mention.url:
                    mention.url = resolved
                    updated += 1
                else:
                    unresolved += 1
                if seen % BATCH == 0:
                    session.commit()
                    print(f"google news backfill: seen={seen} updated={updated} unresolved={unresolved}", flush=True)
        session.commit()
        print(f"google news backfill: seen={seen} updated={updated} unresolved={unresolved}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
