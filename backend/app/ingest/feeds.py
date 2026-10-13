"""Arbitrary RSS/Atom feeds from client settings (source rss_custom).

Each configured URL is fetched once per cycle and parsed with feedparser
(the same parser as the Google News adapter). Entries are keyword-matched
best-effort here; the pipeline re-validates against the active set, as
for every source. A broken feed logs and is skipped — one bad URL must
never stall the cycle.
"""

import logging
from calendar import timegm
from collections.abc import Sequence
from datetime import datetime, timezone

import feedparser
import httpx

from app.ingest.base import RawMention, SourceAdapter
from app.ingest.matching import find_matching_keyword
from app.models.base import MentionSource

log = logging.getLogger("ingest.feeds")

_USER_AGENT = "media-monitor/0.1"
_TIMEOUT_S = 20.0
_MAX_PER_FEED = 100


def _entry_text(entry) -> str:
    """Best-effort body: summary, else content:encoded / content parts."""
    summary = getattr(entry, "summary", None) or ""
    if summary:
        return summary
    content = getattr(entry, "content", None) or []
    for part in content:
        value = getattr(part, "value", None) or (part.get("value") if isinstance(part, dict) else None)
        if value:
            return value
    return ""


def _entry_published(entry) -> datetime | None:
    for stamp in ("published_parsed", "updated_parsed"):
        value = getattr(entry, stamp, None)
        if value:
            try:
                # struct_time is UTC; timegm (unlike mktime) does not shift it.
                return datetime.fromtimestamp(timegm(value), tz=timezone.utc)
            except (OverflowError, ValueError):  # defensive on odd dates
                continue
    return None


def parse_feed(xml_text: str, keywords: Sequence[str]) -> list[RawMention]:
    """Parse one feed's XML into raw mentions (rss_custom source)."""
    feed = feedparser.parse(xml_text)
    mentions: list[RawMention] = []
    for entry in feed.entries:
        url = getattr(entry, "link", "") or ""
        if not url:
            continue
        title = getattr(entry, "title", None) or None
        content = _entry_text(entry) or None
        match_text = "\n".join(part for part in (title, content) if part)
        mentions.append(
            RawMention(
                source=MentionSource.rss_custom,
                keyword=find_matching_keyword(match_text, [str(k) for k in keywords]) or "",
                url=url,
                title=title,
                content=content,
                author=getattr(entry, "author", None) or None,
                published_at=_entry_published(entry),
            )
        )
    return mentions


class FeedsAdapter(SourceAdapter):
    """Polls every client-configured RSS/Atom feed, one request each."""

    name = "rss_custom"

    def __init__(
        self,
        urls: Sequence[str],
        *,
        client: httpx.Client | None = None,
        max_per_feed: int = _MAX_PER_FEED,
    ) -> None:
        self._urls = [url for url in (u.strip() for u in urls) if url]
        self._client = client or httpx.Client(
            headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_S
        )
        self._owns_client = client is None
        self._max_per_feed = max_per_feed

    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
        results: list[RawMention] = []
        try:
            for url in self._urls:
                try:
                    resp = self._client.get(url)
                    resp.raise_for_status()
                    items = parse_feed(resp.text, keywords)
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("feed %s failed: %s", url, exc)
                    continue
                if len(items) > self._max_per_feed:
                    items = items[: self._max_per_feed]
                log.info("feed %s: %d entries", url, len(items))
                results.extend(items)
        finally:
            if self._owns_client:
                self._client.close()
        return results
