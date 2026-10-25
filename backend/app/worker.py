"""Ingest worker entrypoint: APScheduler loop driving all source adapters.

Every INGEST_INTERVAL_MIN minutes, for the configured client:
  1. resolve this cycle's effective settings (DB row; env fallback — see
     app.settings_runtime; the snapshot lives for the cycle only),
  2. load active keywords (client-scoped),
  3. run every enabled adapter (Google News RSS, GDELT, custom RSS feeds,
     Facebook Pages, X provider) — GDELT/pages/feeds per settings,
  4. persist mentions (dedupe on url_hash) with an OpenAI-compatible
     sentiment fallback plus the enrichment pass (sentiment, summary,
     topics and the political v1 label — classifier failures never block
     the row),
  5. hook the alert engine (best-effort), plus the daily retention purge
     and the digest jobs scheduled in the configured timezone.

The X source is settings-driven: free mode rides the x_index adapter,
paid mode uses the twitterapi.io-compatible provider with the key
stored in settings (x_api_key; never serialized). The settings-managed
secrets live plaintext in the DB (v1 scope). The schedule timezone is
read once at startup: changing it in /settings requires a worker reload.
"""

import logging
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import Session

from app.alerts.engine import check_sentiment_shift, run_alert_cycle, run_digest
from app.config import settings
from app.db import SessionLocal
from app.enrich.llm import LLMEnricher
from app.ingest.gdelt import GdeltAdapter
from app.ingest.google_news import GoogleNewsAdapter
from app.ingest.x_index import XIndexAdapter
from app.ingest.pipeline import run_ingest_cycle
from app.models import AlertDigest, queries
from app.models.settings import DEFAULT_TIMEZONE
from app.sentiment.api_analyzer import ApiSentimentAnalyzer
from app.settings_runtime import (
    EffectiveSettings,
    get_effective_settings,
    load_cycle_settings,
    parse_digest_hours,
    resolve_effective_settings,
)
from app import spike
from app.summaries import build_daily_summary, resolve_digest_window, today_in

log = logging.getLogger("worker")

#: Fallback schedule timezone when the DB is unreachable or the stored
#: value is not a valid IANA name (client requirement: 08:00 local).
DIGEST_TIMEZONE = DEFAULT_TIMEZONE

#: Hour (local time) of the daily retention purge.
RETENTION_PURGE_HOUR = 4

#: Minute past the hour for the saved-search spike scan (evaluates the
#: hour that just closed; see app.spike.scan.SCAN_LAG).
SPIKE_SCAN_MINUTE = 9

#: Id prefix of the per-hour digest cron jobs (``digest_summary_<H>``);
#: the schedule resync only touches jobs carrying it.
DIGEST_JOB_PREFIX = "digest_summary_"

#: Minutes between digest-schedule resyncs (settings changes picked up
#: without a worker reload).
DIGEST_SYNC_INTERVAL_MIN = 15

#: Scheduler built by :func:`build_scheduler`; the resync job needs the
#: running instance to add/remove digest crons.
_scheduler: BlockingScheduler | None = None

#: Hour (local time) of the daily summary build (T11). 21:00 keeps the run
#: clearly inside the day it describes while leaving the late evening for
#: ops; the evening tail is covered by regenerating — POST
#: /summaries/generate upserts, so a later rerun folds late mentions in.
DAILY_SUMMARY_HOUR = 21


def build_adapters(effective: EffectiveSettings) -> list:
    """Enabled source adapters from this cycle's effective settings.

    X modes are exclusive: free rides x_index (Google News RSS scoped to
    site:x.com, no key); paid replaces it with the twitterapi.io provider
    keyed from settings. Paid without a stored key NEVER drops coverage —
    one warning, then the free index fallback.
    """
    adapters: list = [GoogleNewsAdapter()]
    if effective.x_mode == "paid" and effective.x_api_key:
        # Imported lazily so the module (and httpx client wiring) only
        # loads when the provider is actually configured.
        from app.ingest.twitter_x import TwitterApiIoProvider

        adapters.append(
            TwitterApiIoProvider(
                api_key=effective.x_api_key,
                base_url=settings.x_provider_base_url,
                rate_per_minute=settings.x_provider_rate_per_min,
            )
        )
    else:
        if effective.x_mode == "paid":
            log.warning(
                "X paid mode enabled but x_api_key is empty; "
                "falling back to the free index adapter (x_index)"
            )
        adapters.append(XIndexAdapter())
    if effective.gdelt_enabled:
        adapters.append(GdeltAdapter())
    else:
        log.info("GDELT disabled by settings (gdelt_enabled=false)")
    if effective.facebook_pages:
        # Imported lazily so the module (and its browser wiring) only
        # loads when a page is actually configured.
        from app.ingest.facebook_public import FacebookPublicAdapter

        adapters.append(FacebookPublicAdapter(pages=list(effective.facebook_pages)))
    else:
        log.info("Facebook Pages disabled: none in settings and FB_PAGES unset")
    if effective.rss_feeds:
        from app.ingest.feeds import FeedsAdapter

        adapters.append(FeedsAdapter(urls=list(effective.rss_feeds)))
    if effective.scrapers:
        # Imported lazily so the module (and its httpx client wiring) only
        # loads when a scraper is actually configured.
        from app.ingest.scrapers import SCRAPER_REGISTRY, ScrapersAdapter

        known = [name for name in effective.scrapers if name in SCRAPER_REGISTRY]
        unknown = sorted(set(effective.scrapers) - set(SCRAPER_REGISTRY))
        if unknown:
            log.warning("unknown scrapers ignored: %s", ", ".join(unknown))
        if known:
            adapters.append(ScrapersAdapter(names=known))
    return adapters


def cycle_sentiment_analyzer(client_id: int):
    """Sentiment fallback for this cycle, from the pinned settings snapshot.

    The enrichment pass owns sentiment (app.sentiment.canonical); this
    API analyzer only covers rows whose enrichment failed or never ran.
    ``None`` (provider local / no key) is fine: those rows stay NULL and
    backfillable — there is no local model anymore.
    """
    effective = get_effective_settings(client_id)
    if effective.ai_provider != "openai" or not effective.ai_api_key:
        return None
    log.info("sentiment fallback analyzer: model=%s", effective.ai_model or "(default)")
    return ApiSentimentAnalyzer(
        api_key=effective.ai_api_key,
        base_url=effective.ai_base_url,
        model=effective.ai_model,
    )


def cycle_enricher(client_id: int) -> tuple[LLMEnricher | None, int]:
    """F2c enrichment pass for this cycle plus the per-cycle call cap.

    Returns ``(None, cap)`` unless an OpenAI-compatible provider with an
    API key is configured — without it rows stay backfillable and the
    classifier columns get nothing on their next reingest.
    """
    effective = get_effective_settings(client_id)
    cap = max(1, int(effective.enrich_max_per_cycle))
    if effective.ai_provider != "openai" or not effective.ai_api_key:
        return None, cap
    log.info("enricher: model=%s cap=%d", effective.ai_model or "(default)", cap)
    return (
        LLMEnricher(
            api_key=effective.ai_api_key,
            base_url=effective.ai_base_url,
            model=effective.ai_model,
        ),
        cap,
    )


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
        keywords = list(queries.list_keywords(session, client.id))
        counts = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=keywords,
            adapters=adapters,
            sentiment_analyzer=analyzer,
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
        if enricher is not None:
            try:
                # Self-heal (enrich-resilience): drain the stale unclassified
                # backlog — per-cycle caps, provider outages and settings
                # windows leave rows NULL; this sweep re-enriches the oldest
                # every cycle. Never fails the cycle.
                from scripts.backfill_enrichment import sweep_backlog

                sweep = sweep_backlog(
                    session, enricher, client_id=client.id, now=cycle_started
                )
                if sweep["candidates"]:
                    log.info("enrich sweep: %s", sweep)
            except Exception:  # noqa: BLE001 - best-effort by design
                log.exception("enrichment sweep failed")
        try:
            # Event-identity arbitrator (T2b): judge the lexical gray band
            # with the fast model, merge/record, all best-effort. Judge
            # failure leaves identity untouched — the deterministic floor.
            from app.ingest.arbitrator import reconcile_gray_pairs

            arbitrated = reconcile_gray_pairs(
                session, client_id=client.id, now=cycle_started
            )
            if arbitrated.get("candidates"):
                log.info("event arbiter: %s", arbitrated)
        except Exception:  # noqa: BLE001 - best-effort by design
            log.exception("event arbiter failed")
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
    generate endpoint would build for the same instant. Returns the row id,
    or None (no row written) when the day has no mentions yet: every cut
    of the day would otherwise keep upserting an empty digest.
    """
    session: Session = SessionLocal()
    try:
        effective = resolve_effective_settings(
            session, client_id=settings.default_client_id
        )
        day = today_in(effective.timezone)
        start, end, _ = resolve_digest_window(
            session, client_id=settings.default_client_id, day=day, tz_name=effective.timezone
        )
        # Same half-open window as the builder; until is inclusive in
        # count_mentions, so shave one microsecond off the end.
        mention_count = queries.count_mentions(
            session,
            settings.default_client_id,
            since=start.astimezone(timezone.utc),
            until=end.astimezone(timezone.utc) - timedelta(microseconds=1),
        )
        if mention_count == 0:
            log.info("daily summary %s skipped: no mentions so far", day)
            return None
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


def _digest_hours() -> list[int]:
    """Digest cut hours from settings; legacy single-hour on any failure.

    The stored ``digest_hours`` CSV is parsed leniently (see
    ``app.settings_runtime.parse_digest_hours``); an empty/unparsable value
    or a DB error falls back to the legacy ``digest_hour`` column and then
    to the hardcoded default, so scheduling always yields >= 1 cut.
    """
    try:
        session: Session = SessionLocal()
        try:
            row = queries.get_settings(session, settings.default_client_id)
        finally:
            session.close()
        hours = parse_digest_hours(row.digest_hours)
        if hours:
            return hours
    except Exception as exc:  # noqa: BLE001 - scheduling must survive a bad DB
        log.warning("could not resolve digest hours (%s); using legacy hour", exc)
    return [_digest_hour()]


def _digest_hour() -> int:
    """Legacy single digest hour from the column, 21 fallback when the DB is unhappy."""
    try:
        session: Session = SessionLocal()
        try:
            row = queries.get_settings(session, settings.default_client_id)
        finally:
            session.close()
        return max(0, min(23, int(row.digest_hour)))
    except Exception as exc:  # noqa: BLE001 - scheduling must survive a bad DB
        log.warning("could not resolve legacy digest hour (%s); using %s", exc, DAILY_SUMMARY_HOUR)
        return DAILY_SUMMARY_HOUR


def _sync_digest_schedule(scheduler) -> None:
    """Align the per-hour digest crons with the configured cut hours.

    Adds a ``digest_summary_<H>`` cron for each desired hour missing and
    removes the scheduled ones no longer configured. Every other job is
    left untouched, so a settings change never resets the ingest loop.
    """
    desired = set(_digest_hours())
    scheduled: set[int] = set()
    for job in scheduler.get_jobs():
        job_id = str(job.id)
        if not job_id.startswith(DIGEST_JOB_PREFIX):
            continue
        try:
            scheduled.add(int(job_id[len(DIGEST_JOB_PREFIX) :]))
        except ValueError:
            continue  # foreign job sharing the prefix: leave it alone
    tz_name = _schedule_timezone()
    for hour in sorted(desired - scheduled):
        scheduler.add_job(
            daily_summary_job,
            "cron",
            hour=hour,
            minute=0,
            timezone=tz_name,
            id=f"{DIGEST_JOB_PREFIX}{hour}",
            max_instances=1,
            coalesce=True,
        )
        log.info("digest schedule: added %sh cut", f"{hour:02d}")
    for hour in sorted(scheduled - desired):
        try:
            scheduler.remove_job(f"{DIGEST_JOB_PREFIX}{hour}")
        except JobLookupError:
            continue  # removed concurrently: nothing to do
        log.info("digest schedule: removed %sh cut", f"{hour:02d}")


def _sync_digest_schedule_job() -> None:
    """15-min interval hook keeping the digest crons in sync (T2)."""
    if _scheduler is None:  # pragma: no cover - only before build_scheduler
        return
    try:
        _sync_digest_schedule(_scheduler)
    except Exception:  # noqa: BLE001 - resync must never kill the loop
        log.exception("digest schedule resync failed")


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
    # One digest cron per configured cut; the resync job keeps them aligned
    # with settings changes without ever touching the jobs above.
    for hour in _digest_hours():
        scheduler.add_job(
            daily_summary_job,
            "cron",
            hour=hour,
            minute=0,
            timezone=tz_name,
            id=f"{DIGEST_JOB_PREFIX}{hour}",
            max_instances=1,
            coalesce=True,
        )
    scheduler.add_job(
        _sync_digest_schedule_job,
        "interval",
        minutes=DIGEST_SYNC_INTERVAL_MIN,
        id="digest_schedule_sync",
        max_instances=1,
        coalesce=True,
    )
    global _scheduler  # noqa: PLW0603 - module-level handle for the resync
    _scheduler = scheduler
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
