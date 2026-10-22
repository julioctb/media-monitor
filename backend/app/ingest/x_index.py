"""X (Twitter) coverage via the Google News index — free, no API key.

The paid provider (ingest/twitter_x.py) stays dormant without
X_PROVIDER_API_KEY, which left the monitor with zero X coverage. This
adapter fills that gap at $0 the same way the Hermes digest cron does:
Google News indexes x.com, so scoping the RSS query with `site:x.com`
returns real tweets (verified live 22/oct/2026: 100/100 items for
"BUAP site:x.com"). Tradeoffs, identical to google_news mentions: <link>
stays a news.google.com redirect, <source> carries no author handle
(just "X"), and titles arrive with a " - X" suffix that is stripped
here. Additive to twitter_x: both can run together when the key exists.
"""

import logging
from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime

import httpx

from app.ingest.base import RawMention
from app.ingest.google_news import (
    GOOGLE_NEWS_RSS_URL,
    _TIMEOUT_S,
    _USER_AGENT,
    GoogleNewsAdapter,
    _now_utc,
    parse_google_rss,
)
from app.models.base import MentionSource

log = logging.getLogger("ingest.x_index")

_TITLE_SUFFIX = " - X"


def _strip_x_suffix(title: str | None) -> str | None:
    if title is None or not title.endswith(_TITLE_SUFFIX):
        return title
    return title[: -len(_TITLE_SUFFIX)]


def _as_x_mention(item: RawMention) -> RawMention:
    """Re-tag a parsed news item as an X mention with a clean title."""
    return replace(
        item,
        source=MentionSource.x_twitter,
        title=_strip_x_suffix(item.title),
    )


class XIndexAdapter(GoogleNewsAdapter):
    """Google News RSS scoped to x.com: X mentions at $0, no credentials.

    Inherits the parent's localization (hl/gl/ceid), redirect handling,
    watermark window (`when:<N>h`), per-keyword error isolation and
    max_items; only the query template differs ('"<keyword>" site:x.com'
    plus the ' - X' title strip and the x_twitter source tag). fetch is
    re-implemented because the parent builds the query inline.
    """

    name = "x_index"

    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
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
                    "hl": self._hl,
                    "gl": self._gl,
                    "ceid": self._ceid,
                }
                query = f'"{keyword}" site:x.com'
                if since is not None:
                    # Same hour-granular watermark window as google_news;
                    # pipeline dedupe remains the boundary guarantee.
                    elapsed_h = max(1, (_now_utc() - since).days * 24 + 1)
                    query = f"{query} when:{elapsed_h}h"
                params["q"] = query
                try:
                    # Google News 302s hl=es to hl=es-419; follow it.
                    resp = client.get(
                        GOOGLE_NEWS_RSS_URL, params=params, follow_redirects=True
                    )
                    resp.raise_for_status()
                    items = parse_google_rss(resp.text, keyword)
                except httpx.HTTPError as exc:
                    log.warning("x index fetch failed for %r: %s", keyword, exc)
                    continue
                results.extend(_as_x_mention(i) for i in items[: self._max_items])
        finally:
            if owns_client:
                client.close()
        return results
