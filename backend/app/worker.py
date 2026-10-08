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

from app.alerts.engine import run_alert_cycle, run_digest
from app.config import settings
from app.db import SessionLocal
from app.ingest.gdelt import GdeltAdapter
from app.ingest.google_news import GoogleNewsAdapter
from app.ingest.pipeline import run_ingest_cycle
from app.models import AlertDigest, queries

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
    """One ingest cycle for the default client, then the alert hook.

    Returns per-adapter inserted counts. The alert pass (instant email or
    digest pending-marker) is best-effort: it must never fail the cycle.
    """
    cycle_started = datetime.now(tz=timezone.utc)
    adapters = build_adapters()
    analyzer = get_sentiment_analyzer()
    session: Session = SessionLocal()
    try:
        client = queries.get_or_create_client(session, "default")
        keywords = list(queries.list_keywords(session, client.id))
        counts = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=keywords,
            adapters=adapters,
            sentiment_analyzer=analyzer,
        )
        try:
            run_alert_cycle(session, cycle_started_at=cycle_started, client_id=client.id)
        except Exception:  # noqa: BLE001 - alerts are best-effort by design
            log.exception("alert cycle failed")
        return counts
    finally:
        session.close()


DIGEST_TIMEZONE = "America/Mexico_City"  # client requirement: 08:00 local


def _daily_digest_job() -> None:
    run_digest(AlertDigest.daily)


def _weekly_digest_job() -> None:
    run_digest(AlertDigest.weekly)


def build_scheduler() -> BlockingScheduler:
    """Ingest interval job plus the two digest cron jobs (08:00 CDMX)."""
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
    scheduler.add_job(
        _daily_digest_job,
        "cron",
        hour=8,
        minute=0,
        timezone=DIGEST_TIMEZONE,
        id="alerts_daily",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        _weekly_digest_job,
        "cron",
        day_of_week="mon",
        hour=8,
        minute=0,
        timezone=DIGEST_TIMEZONE,
        id="alerts_weekly",
        max_instances=1,
        coalesce=True,
    )
    return scheduler


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    scheduler = build_scheduler()
    log.info(
        "worker scheduled (jobs=%s, ingest_interval=%s min)",
        [job.id for job in scheduler.get_jobs()],
        settings.ingest_interval_min,
    )
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("worker stopped")


if __name__ == "__main__":
    main()
