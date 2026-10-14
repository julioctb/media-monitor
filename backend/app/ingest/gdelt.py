"""GDELT 2.0 DOC API adapter (free, no auth).

Endpoint: https://api.gdeltproject.org/api/v2/doc/doc
          ?query=<query>&mode=artlist&format=json&timespan=15min

GDELT returns a JSON article list. Language is filtered server-side with
`sourcelang:spanish` OR english via the query string. Items whose URL was
already ingested are dropped by the pipeline's url_hash dedupe.
"""

import logging
import time
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

import httpx

from app.ingest.base import RawMention, SourceAdapter
from app.models.base import MentionSource

log = logging.getLogger("ingest.gdelt")

GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
_TIMEOUT_S = 20.0


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


def build_gdelt_query(keyword: str) -> str:
    """GDELT query for a keyword restricted to ES+EN sources, last 15 min."""
    return f'"{keyword}" (sourcelang:spanish OR sourcelang:english)'


def parse_gdelt_payload(payload: dict, keyword: str) -> list[RawMention]:
    """Map a GDELT artlist JSON payload to raw mentions."""
    articles = payload.get("articles") or []
    mentions: list[RawMention] = []
    for art in articles:
        url = art.get("url") or ""
        if not url:
            continue
        published_at = None
        seendate = art.get("seendate")  # format: 20261008T121500Z
        if isinstance(seendate, str) and len(seendate) >= 15:
            try:
                published_at = datetime.strptime(seendate[:15], "%Y%m%dT%H%M%S").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                published_at = None
        mentions.append(
            RawMention(
                source=MentionSource.gdelt,
                keyword=keyword,
                url=url,
                title=art.get("title") or None,
                content=art.get("snippet") or None,
                lang=art.get("language") or None,
                published_at=published_at,
                raw={
                    "domain": art.get("domain"),
                    "sourcecountry": art.get("sourcecountry"),
                },
            )
        )
    return mentions


class GdeltAdapter(SourceAdapter):
    """Polls the GDELT 2.0 DOC API artlist for each keyword.

    GDELT enforces one request every 5 seconds per client: the keyword loop
    sleeps between requests and retries 429s with backoff (a rate-limited
    keyword used to come back as a plain-text notice, not JSON, and the
    whole run silently degraded to 0 items — seen in prod 2026-10-14).
    """

    name = "gdelt"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        timespan: str = "15min",
        max_items: int = 75,
        pause_s: float = 5.5,
        sleep: Callable[[float], None] = time.sleep,
        attempts: int = 3,
    ) -> None:
        self._client = client
        self._timespan = timespan
        self._max_items = max_items
        self._pause_s = pause_s
        self._sleep = sleep
        self._attempts = max(1, attempts)

    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
        client = self._client or httpx.Client(timeout=_TIMEOUT_S)
        owns_client = self._client is None
        timespan = self._timespan
        if since is not None:
            # Narrow the artlist window to the ingest watermark (hours
            # granularity, clamped to GDELT's supported range); url_hash
            # dedupe covers the boundary.
            elapsed_s = max(0, (_now_utc() - since).total_seconds())
            minutes = min(1440, max(15, int(elapsed_s // 60) + 15))
            timespan = f"{minutes}min"
        results: list[RawMention] = []
        try:
            for index, keyword in enumerate(keywords):
                keyword = str(keyword).strip()
                if not keyword:
                    continue
                if index:
                    # Courtesy pause: one request / 5 s, not per-cycle.
                    self._sleep(self._pause_s)
                params = {
                    "query": build_gdelt_query(keyword),
                    "mode": "artlist",
                    "format": "json",
                    "timespan": timespan,
                    "maxrecords": str(self._max_items),
                }
                payload = None
                for attempt in range(self._attempts):
                    if attempt:
                        # 429 backoff: GDELT answers plain text, not JSON.
                        self._sleep(self._pause_s * attempt)
                    try:
                        resp = client.get(GDELT_DOC_URL, params=params)
                        resp.raise_for_status()
                        payload = resp.json()
                    except (httpx.HTTPError, ValueError) as exc:
                        log.warning("gdelt fetch failed for %r: %s", keyword, exc)
                        continue
                    break
                if not isinstance(payload, dict):
                    continue
                results.extend(parse_gdelt_payload(payload, keyword)[: self._max_items])
        finally:
            if owns_client:
                client.close()
        return results
