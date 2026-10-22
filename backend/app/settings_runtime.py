"""Effective settings for the ingest cycle: DB row over env fallback.

The settings row always wins. Environment variables fill gaps only where
the stored value is empty — today that is FB_PAGES when the row carries
no facebook pages (ai_* / retention / timezone have no env counterparts).

The resolved snapshot is cached per client for exactly one ingest cycle:
``load_cycle_settings`` pins it at cycle start and
``get_effective_settings`` serves the cached copy to the rest of the
cycle (adapters, sentiment factory). The next cycle's load overwrites
it, so API-driven settings changes are picked up at most one cycle late
and never within a cycle.
"""

import logging
from dataclasses import dataclass, field

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import settings as env_settings
from app.ingest.facebook_public import FacebookPageTarget
from app.models import queries
from app.models.settings import DEFAULT_TIMEZONE

log = logging.getLogger("settings.runtime")


@dataclass(frozen=True)
class EffectiveSettings:
    """Immutable per-cycle settings snapshot (defaults = safe empty config)."""

    client_id: int
    client_name: str = ""
    timezone: str = DEFAULT_TIMEZONE
    retention_days: int = 365
    digest_hour: int = 21
    # Daily digest cut hours (0..23, ascending, deduped). Parsed from the
    # stored CSV; digest_hour above mirrors the first cut for compat.
    digest_hours: list[int] = field(default_factory=lambda: [21])
    digest_focus_person_id: int | None = None
    gdelt_enabled: bool = True
    facebook_pages: tuple[FacebookPageTarget, ...] = ()
    rss_feeds: tuple[str, ...] = ()
    scrapers: tuple[str, ...] = ()
    ai_provider: str = "local"
    ai_api_key: str | None = None
    ai_base_url: str | None = None
    ai_model: str | None = None
    enrich_max_per_cycle: int = 50
    fetch_max_per_cycle: int = 20


# Cycle-scoped cache: client_id -> snapshot. Overwritten by every
# load_cycle_settings; never consulted across cycles for freshness.
_cycle_cache: dict[int, EffectiveSettings] = {}


def _pages_from_row(row) -> tuple[FacebookPageTarget, ...]:
    pages: list[FacebookPageTarget] = []
    for entry in row.facebook_pages or []:
        if isinstance(entry, FacebookPageTarget):
            pages.append(entry)
            continue
        try:
            # Legacy rows carry token/kind extras: pydantic ignores them.
            pages.append(FacebookPageTarget(**entry))
        except (TypeError, ValidationError) as exc:
            log.warning("settings: skipping malformed facebook page %s: %s", entry, exc)
    return tuple(pages)


def parse_digest_hours(raw: object) -> list[int]:
    """Parse the stored ``digest_hours`` CSV into safe cut hours.

    Accepts the raw column value (str) or an iterable of ints: entries are
    coerced per item, out-of-range and non-numeric tokens are dropped and
    the rest is deduped and sorted. Empty/invalid input yields ``[]`` so
    callers can apply their own fallback (legacy ``digest_hour``).
    """
    if isinstance(raw, str):
        tokens: list[object] = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                tokens.append(int(token))
            except ValueError:
                continue  # hand-edited row: drop the junk, keep the rest
    elif isinstance(raw, (list, tuple)):
        tokens = list(raw)
    else:
        return []
    hours: list[int] = []
    for token in tokens:
        if isinstance(token, bool) or not isinstance(token, int):
            continue
        if 0 <= token <= 23 and token not in hours:
            hours.append(token)
    return sorted(hours)


def resolve_effective_settings(session: Session, client_id: int) -> EffectiveSettings:
    """DB row first; env only fills fields the row leaves empty."""
    row = queries.get_settings(session, client_id)
    pages = _pages_from_row(row)
    if not pages and env_settings.fb_pages:
        log.info(
            "settings: no facebook pages in DB for client %s; using FB_PAGES env (%d)",
            client_id,
            len(env_settings.fb_pages),
        )
        pages = tuple(env_settings.fb_pages)
    # Clamp on read too: a hand-edited row must not break scheduling. The
    # cut list wins; legacy digest_hour is the fallback when the CSV is
    # empty/unparsable, and mirrors the first cut otherwise.
    legacy_hour = max(0, min(23, row.digest_hour))
    digest_hours = parse_digest_hours(row.digest_hours) or [legacy_hour]
    return EffectiveSettings(
        client_id=client_id,
        client_name=row.client_name,
        timezone=row.timezone,
        retention_days=row.retention_days,
        digest_hour=digest_hours[0],
        digest_hours=digest_hours,
        digest_focus_person_id=row.digest_focus_person_id,
        gdelt_enabled=row.gdelt_enabled,
        facebook_pages=pages,
        rss_feeds=tuple(row.rss_feeds or []),
        scrapers=tuple(row.scrapers or []),
        ai_provider=row.ai_provider,
        ai_api_key=row.ai_api_key,
        ai_base_url=row.ai_base_url,
        ai_model=row.ai_model,
        enrich_max_per_cycle=row.enrich_max_per_cycle,
        fetch_max_per_cycle=row.fetch_max_per_cycle,
    )


def load_cycle_settings(session: Session, *, client_id: int) -> EffectiveSettings:
    """Resolve, pin and return this cycle's snapshot for the client."""
    effective = resolve_effective_settings(session, client_id)
    _cycle_cache[client_id] = effective
    return effective


def get_effective_settings(client_id: int) -> EffectiveSettings:
    """The pinned snapshot for the running cycle (see module docstring)."""
    try:
        return _cycle_cache[client_id]
    except KeyError as exc:
        raise RuntimeError(
            "cycle settings not loaded; call load_cycle_settings at cycle start"
        ) from exc
