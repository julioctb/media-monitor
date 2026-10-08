"""Ingest worker entrypoint: APScheduler loop driving all source adapters.

Every INGEST_INTERVAL_MIN minutes, for the configured client:
  1. load active keywords (client-scoped),
  2. run every enabled adapter (Google News RSS, GDELT, X provider),
  3. persist mentions (dedupe on url_hash) with sentiment scoring.

The X provider adapter is skipped (with a single log line) when
X_PROVIDER_API_KEY is unset. Sentiment runs lazily: the analyzer model is
loaded on first use, and unit tests inject a mock analyzer.
"""

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.ingest.gdelt import GdeltAdapter
from app.ingest.google_news import GoogleNewsAdapter
from app.ingest.pipeline import run_ingest_cycle
from app.models import queries

log = logging.getLogger("worker")


def build_adapters() -> list:
    """Enabled source adapters based on current settings."""
    adapters: list = [GoogleNewsAdapter(), GdeltAdapter()]
    if not settings.x_provider_api_key:
        log.info("X provider disabled: X_PROVIDER_API_KEY not set")
        return adapters
    # Imported lazily so the module (and httpx client wiring) only loads
    # when the provider is actually configured.
    from app.ingest.twitter_x import TwitterApiIoProvider

    adapters.append(
        TwitterApiIoProvider(
            api_key=settings.x_provider_api_key,
            base_url=settings.x_provider_base_url,
            rate_per_minute=settings.x_provider_rate_per_min,
        )
    )
    return adapters


def get_sentiment_analyzer():
    """Lazily constructed sentiment analyzer (never loads a model at import)."""
    from app.sentiment.laya_analyzer import LayaAnalyzer

    return LayaAnalyzer()


def ingest_job() -> dict[str, int]:
    """One ingest cycle for the default client. Returns per-adapter counts."""
    adapters = build_adapters()
    analyzer = get_sentiment_analyzer()
    session: Session = SessionLocal()
    try:
        client = queries.get_or_create_client(session, "default")
        keywords = list(queries.list_keywords(session, client.id))
        return run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=keywords,
            adapters=adapters,
            sentiment_analyzer=analyzer,
        )
    finally:
        session.close()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    scheduler = BlockingScheduler(timezone="UTC")
    scheduler.add_job(
        ingest_job,
        "interval",
        minutes=max(1, settings.ingest_interval_min),
        id="ingest_cycle",
        max_instances=1,
        coalesce=True,
        next_run_time=datetime.now(tz=timezone.utc),
    )
    log.info(
        "ingest worker started (interval=%s min, adapters=%s)",
        settings.ingest_interval_min,
        [a.name for a in build_adapters()],
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("ingest worker stopped")


if __name__ == "__main__":
    main()
