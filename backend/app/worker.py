"""Ingest worker entrypoint: APScheduler loop driving all source adapters.

Every INGEST_INTERVAL_MIN minutes, for the configured client:
  1. resolve this cycle's effective settings (DB row; env fallback — see
     app.settings_runtime; the snapshot lives for the cycle only),
  2. load active keywords (client-scoped),
  3. run every enabled adapter (Google News RSS, GDELT, custom RSS feeds,
     Facebook Pages, X provider) — GDELT/pages/feeds per settings,
  4. persist mentions (dedupe on url_hash) with the cycle's sentiment
     analyzer (local Laya, or an OpenAI-compatible API with optional
     local fallback), then run the classifier registry over each new
     mention (political v1; classifier failures never block the row),
  5. hook the alert engine (best-effort), plus the daily retention purge
     and the digest jobs scheduled in the configured timezone.

The X provider stays env-keyed (X_PROVIDER_*); the settings-managed
secrets live plaintext in the DB (v1 scope). The schedule timezone is
read once at startup: changing it in /settings requires a worker reload.
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from app.alerts.engine import check_sentiment_shift, run_alert_cycle, run_digest
from app.classifications import build_classifiers
from app.config import settings
from app.db import SessionLocal
from app.enrich.llm import LLMEnricher
from app.ingest.gdelt import GdeltAdapter
from app.ingest.google_news import GoogleNewsAdapter
from app.ingest.pipeline import run_ingest_cycle
from app.models import AlertDigest, queries
from app.models.settings import DEFAULT_TIMEZONE
from app.sentiment.factory import build_sentiment_analyzer
from app.settings_runtime import (
    EffectiveSettings,
    get_effective_settings,
    load_cycle_settings,
    resolve_effective_settings,
)
from app import spike
from app.summaries import build_daily_summary, today_in

log = logging.getLogger("worker")

#: Fallback schedule timezone when the DB is unreachable or the stored
#: value is not a valid IANA name (client requirement: 08:00 local).
DIGEST_TIMEZONE = DEFAULT_TIMEZONE

#: Hour (local time) of the daily retention purge.
RETENTION_PURGE_HOUR = 4

#: Minute past the hour for the saved-search spike scan (evaluates the
#: hour that just closed; see app.spike.scan.SCAN_LAG).
SPIKE_SCAN_MINUTE = 9

#: Hour (local time) of the daily summary build (T11). 21:00 keeps the run
#: clearly inside the day it describes while leaving the late evening for
#: ops; the evening tail is covered by regenerating — POST
#: /summaries/generate upserts, so a later rerun folds late mentions in.
DAILY_SUMMARY_HOUR = 21


def build_adapters(effective: EffectiveSettings) -> list:
    """Enabled source adapters from this cycle's effective settings."""
    adapters: list = [GoogleNewsAdapter()]
    if effective.gdelt_enabled:
        adapters.append(GdeltAdapter())
    else:
        log.info("GDELT disabled by settings (gdelt_enabled=false)")
    if effective.facebook_pages:
        # Imported lazily so the module (and its httpx client wiring) only
        # loads when a page is actually configured.
        from app.ingest.facebook_page import FacebookPageAdapter

        adapters.append(
            FacebookPageAdapter(
                pages=list(effective.facebook_pages),
                graph_version=settings.fb_graph_api_version,
            )
        )
    else:
        log.info("Facebook Pages disabled: none in settings and FB_PAGES unset")
    if effective.rss_feeds:
        from app.ingest.feeds import FeedsAdapter

        adapters.append(FeedsAdapter(urls=list(effective.rss_feeds)))
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


def cycle_sentiment_analyzer(client_id: int):
    """Analyzer for this cycle, built from the pinned settings snapshot."""
    effective = get_effective_settings(client_id)
    log.info(
        "sentiment analyzer: provider=%s model=%s fallback_local=%s",
        effective.ai_provider,
        effective.ai_model or "(default)",
        effective.ai_fallback_local,
    )
    return build_sentiment_analyzer(
        provider=effective.ai_provider,
        api_key=effective.ai_api_key,
        base_url=effective.ai_base_url,
        model=effective.ai_model,
        fallback_local=effective.ai_fallback_local,
    )


def cycle_enricher(client_id: int) -> tuple[LLMEnricher | None, int]:
    """F2c enrichment pass for this cycle plus the per-cycle call cap.

    Returns ``(None, cap)`` unless an OpenAI-compatible provider with an
    API key is configured — without it the pipeline degrades to the plain
    sentiment path and rows stay backfillable. The agreement analyzer
    (TE5) is the local laya analyzer, logging enrichment-vs-laya for the
    switch-off decision; it loads lazily so a cycle without enrichments
    never pays for the model.
    """
    effective = get_effective_settings(client_id)
    cap = max(1, int(effective.enrich_max_per_cycle))
    if effective.ai_provider != "openai" or not effective.ai_api_key:
        return None, cap
    log.info(
        "enricher: model=%s cap=%d agreement=laya",
        effective.ai_model or "(default)",
        cap,
    )
    from app.sentiment.laya_analyzer import LayaAnalyzer

    enricher = LLMEnricher(
        api_key=effective.ai_api_key,
        base_url=effective.ai_base_url,
        model=effective.ai_model,
        agreement_analyzer=LayaAnalyzer(),
    )
    return enricher, cap


def ingest_job() -> dict[str, int]:
    """One ingest cycle for the default client, then the alert hook.

    Returns per-adapter inserted counts. The alert pass (instant email or
    digest pending-marker) is best-effort: it must never fail the cycle.
    """
    cycle_started = datetime.now(tz=timezone.utc)
    session: Session = SessionLocal()
    try:
        client = queries.get_or_create_client(session, "default")
        # Pin this cycle's settings snapshot before building anything.
        effective = load_cycle_settings(session, client_id=client.id)
        adapters = build_adapters(effective)
        analyzer = cycle_sentiment_analyzer(client.id)
        enricher, enrich_limit = cycle_enricher(client.id)
        classifiers = build_classifiers()
        keywords = list(queries.list_keywords(session, client.id))
        counts = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=keywords,
            adapters=adapters,
            sentiment_analyzer=analyzer,
            classifiers=classifiers,
            enricher=enricher,
            enrich_limit=enrich_limit,
            fetch_limit=max(1, int(effective.fetch_max_per_cycle)),
            cycle_started=cycle_started,
        )
        try:
            run_alert_cycle(session, cycle_started_at=cycle_started, client_id=client.id)
        except Exception:  # noqa: BLE001 - alerts are best-effort by design
            log.exception("alert cycle failed")
        try:
            # T4 sentiment-shift rule; the watermark inside keeps this quiet
            # to one send per window.
            check_sentiment_shift(session, client_id=client.id, now=cycle_started)
        except Exception:  # noqa: BLE001 - best-effort by design
            log.exception("sentiment shift check failed")
        return counts
    finally:
        session.close()


def retention_purge_job() -> int | None:
    """Daily retention sweep: delete mentions older than retention_days.

    retention_days == 0 disables the purge (keep everything). Returns the
    removed count, or None when disabled.
    """
    session: Session = SessionLocal()
    try:
        row = queries.get_settings(session, settings.default_client_id)
        if row.retention_days <= 0:
            log.info("retention purge disabled (retention_days=0)")
            return None
        cutoff = queries.retention_cutoff(row.retention_days)
        deleted = queries.purge_mentions_before(
            session, client_id=row.client_id, older_than=cutoff
        )
        log.info(
            "retention purge: removed %d mention(s) older than %d day(s)",
            deleted,
            row.retention_days,
        )
        return deleted
    finally:
        session.close()


def spike_scan_job() -> int:
    """Hourly saved-search spike scan; returns the new spike events count.

    Persistence and dedupe live in app.spike.scan; failures there are
    contained per saved search, so the job itself only guards the session.
    """
    session: Session = SessionLocal()
    try:
        events = spike.run_spike_scan(session)
        if events:
            log.info(
                "spike scan: %d new event(s): %s",
                len(events),
                [(e.saved_search_id, e.window_start.isoformat()) for e in events],
            )
        return len(events)
    finally:
        session.close()


def daily_summary_job() -> int | None:
    """Build (or regenerate) today's summary for the default client (T11).

    Both the day and the mention window follow the settings timezone via
    app.summaries (today_in / day_window), matching what the API's
    generate endpoint would build for the same instant. Returns the row id.
    """
    session: Session = SessionLocal()
    try:
        effective = resolve_effective_settings(
            session, client_id=settings.default_client_id
        )
        day = today_in(effective.timezone)
        row = build_daily_summary(
            session, client_id=settings.default_client_id, day=day
        )
        log.info("daily summary %s built (mode=%s, id=%s)", day, row.mode, row.id)
        return row.id
    finally:
        session.close()


def _daily_digest_job() -> None:
    run_digest(AlertDigest.daily)


def _weekly_digest_job() -> None:
    run_digest(AlertDigest.weekly)


def _schedule_timezone() -> str:
    """Schedule timezone from the settings row, validated via zoneinfo."""
    try:
        session: Session = SessionLocal()
        try:
            row = queries.get_settings(session, settings.default_client_id)
        finally:
            session.close()
        ZoneInfo(row.timezone)  # validate before scheduling with it
        return row.timezone
    except Exception as exc:  # noqa: BLE001 - scheduling must survive a bad DB
        log.warning("could not resolve schedule timezone (%s); using %s", exc, DIGEST_TIMEZONE)
        return DIGEST_TIMEZONE


def build_scheduler() -> BlockingScheduler:
    """Ingest interval, both digest crons and the retention purge."""
    tz_name = _schedule_timezone()
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
        timezone=tz_name,
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
        timezone=tz_name,
        id="alerts_weekly",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        spike_scan_job,
        "cron",
        minute=SPIKE_SCAN_MINUTE,
        timezone="UTC",
        id="spike_scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        retention_purge_job,
        "cron",
        hour=RETENTION_PURGE_HOUR,
        minute=0,
        timezone=tz_name,
        id="retention_purge",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        daily_summary_job,
        "cron",
        hour=DAILY_SUMMARY_HOUR,
        minute=0,
        timezone=tz_name,
        id="daily_summary",
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
