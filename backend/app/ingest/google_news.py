"""Google News RSS adapter (free, no auth).

Endpoint: https://news.google.com/rss/search?q=<query>&hl=es&gl=MX&ceid=MX:es
Parsed with feedparser. One request per keyword: Google News OR queries
return one blended list that loses which keyword matched, and per-keyword
requests keep request count proportional to tracked terms anyway.
"""

import logging
from collections.abc import Sequence
from calendar import timegm
from datetime import datetime, timezone

import feedparser
import httpx

from app.ingest.base import RawMention, SourceAdapter
from app.models.base import MentionSource

log = logging.getLogger("ingest.google_news")

GOOGLE_NEWS_RSS_URL = "https://news.google.com/rss/search"
_USER_AGENT = "media-monitor/0.1"
_TIMEOUT_S = 20.0


def parse_google_rss(xml_text: str, keyword: str) -> list[RawMention]:
    """Parse Google News RSS XML into raw mentions for one keyword."""
    feed = feedparser.parse(xml_text)
    mentions: list[RawMention] = []
    for entry in feed.entries:
        url = getattr(entry, "link", "") or ""
        title = getattr(entry, "title", "") or None
        if not url:
            continue
        published_at = None
        if getattr(entry, "published_parsed", None):
            try:
                # published_parsed is UTC; timegm (unlike mktime) does not
                # shift it by the local timezone.
                published_at = datetime.fromtimestamp(
                    timegm(entry.published_parsed), tz=timezone.utc
                )
            except (OverflowError, ValueError):  # defensive on odd dates
                published_at = None
        mentions.append(
            RawMention(
                source=MentionSource.news_rss,
                keyword=keyword,
                url=url,
                title=title,
                lang="es",
                published_at=published_at,
            )
        )
    return mentions


class GoogleNewsAdapter(SourceAdapter):
    """Polls Google News RSS, one query per keyword,hl/gl/ceid localized."""

    name = "google_news"

    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        hl: str = "es",
        gl: str = "MX",
        ceid: str = "MX:es",
        max_items: int = 50,
    ) -> None:
        self._client = client
        self._hl, self._gl, self._ceid = hl, gl, ceid
        self._max_items = max_items

    def fetch(self, keywords: Sequence[str]) -> list[RawMention]:
        client = self._client or httpx.Client(
            headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT_S
        )
        owns_client = self._client is None
        results: list[RawMention] = []
        try:
            for keyword in keywords:
                keyword = str(keyword).strip()
                if not keyword:
                    continue
                params = {
                    "q": f'"{keyword}"',
                    "hl": self._hl,
                    "gl": self._gl,
                    "ceid": self._ceid,
                }
                try:
                    resp = client.get(GOOGLE_NEWS_RSS_URL, params=params)
                    resp.raise_for_status()
                    items = parse_google_rss(resp.text, keyword)
                except httpx.HTTPError as exc:
                    log.warning("google news fetch failed for %r: %s", keyword, exc)
                    continue
                results.extend(items[: self._max_items])
        finally:
            if owns_client:
                client.close()
        return results
