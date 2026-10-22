"""Facebook public-page ingest via headless Chromium (no tokens, no Graph).

Scrapes the public timeline of each configured page id with Playwright and
parses the rendered articles. Replaces the token-based Graph adapter: the
app monitors third-party pages, which need the Page Public Content Access
review on Graph but are readable from the public HTML the browser sees.

Logged-out timelines render only the first screenful of posts: enough for
a 15-minute incremental cycle (new posts are always at the top), not for
backfill.

``data-utime`` (unix epoch) is the primary timestamp; the relative label
("hace 2 h") is the fallback; None otherwise — the digest already tolerates
mentions without published_at via the ingest watermark. Observed on the
2026-10-22 public wall: permalinks come as ``permalink.php?story_fbid=...``
and neither ``data-utime`` nor ``<time>`` elements exist.
"""

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.ingest.base import RawMention
from app.ingest.matching import find_matching_keyword
from app.models.base import MentionSource

log = logging.getLogger("ingest.facebook_public")

FB_PAGE_URL = "https://www.facebook.com/{page_id}/"
MAX_POSTS_PER_PAGE = 15  # first screenful is enough for an incremental cycle

_RELATIVE = re.compile(
    r"hace\s+(\d+)\s*(minutos?|min|horas?|h|d[ií]as?|d|semanas?|s)\b", re.I
)

_PERMALINK_SEL = (
    'a[href*="/posts/"], a[href*="/permalink/"], '
    'a[href*="/videos/"], a[href*="permalink.php"]'
)

_EXTERNAL_ID_RE = re.compile(r"/(?:posts|permalink|videos)/(?:[^/?#]*?[pbmid]\.)?(\d+)")

_TRAILING_CHROME_RE = re.compile(r"\s*Ver más\s*$")

_RELATIVE_UNITS = {
    "min": "minutes",
    "minuto": "minutes",
    "minutos": "minutes",
    "h": "hours",
    "hora": "hours",
    "horas": "hours",
    "d": "days",
    "día": "days",
    "días": "days",
    "s": "seconds",
    "semana": "weeks",
    "semanas": "weeks",
}


def _parse_relative(label: str, now: datetime) -> datetime | None:
    """Turn a Facebook relative label ("hace 2 horas") into an absolute utc dt."""
    m = _RELATIVE.search(label or "")
    if not m:
        return None
    amount = int(m.group(1))
    unit = _RELATIVE_UNITS.get(m.group(2).lower())
    if unit is None:
        return None
    return now - timedelta(**{unit: amount})


def _external_id(url: str) -> str | None:
    """Stable id: story_fbid for permalink.php, path digits otherwise."""
    qs = parse_qs(urlparse(url).query)
    story = (qs.get("story_fbid") or [None])[0]
    if story:
        return str(story)
    m = _EXTERNAL_ID_RE.search(url)
    return m.group(1) if m else None


def _post_text(article: Any) -> str:
    """Longest auto-directional span = the post's message (titles/counts are
    shorter); falls back to the whole article text if empty."""
    spans = [s.get_text(" ", strip=True) for s in article.select('span[dir="auto"]')]
    spans = [s for s in spans if len(s) >= 15]
    if spans:
        return _TRAILING_CHROME_RE.sub("", max(spans, key=len)).strip()
    return article.get_text(" ", strip=True)[:500]


def _created_at(article: Any, now: datetime) -> datetime | None:
    """``data-utime`` epoch first, then a relative label; None otherwise."""
    utime = article.select_one("[data-utime]")
    if utime is not None:
        raw = str(utime.get("data-utime", ""))
        if raw.isdigit():
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
    for span in article.select('span[dir="auto"]'):
        parsed = _parse_relative(span.get_text(" ", strip=True), now)
        if parsed is not None:
            return parsed
    return None


def extract_posts(html: str) -> list[dict[str, Any]]:
    """Parse the rendered timeline HTML into post dicts.

    Returns at most ``MAX_POSTS_PER_PAGE`` entries keyed
    ``url / external_id / text / created_at``; nested comment articles
    repeating an already-seen permalink are dropped.
    """
    soup = BeautifulSoup(html, "lxml")
    now = datetime.now(timezone.utc)
    posts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for art in soup.select('div[role="article"]'):
        link = art.select_one(_PERMALINK_SEL)
        if link is None:
            continue
        href = link.get("href", "")
        url = f"https://www.facebook.com{href}" if href.startswith("/") else href
        external_id = _external_id(url)
        # Nested comment articles repeat the story with a different query
        # string: dedupe on the stable id, not the raw URL.
        if not external_id or external_id in seen:
            continue
        seen.add(external_id)
        posts.append(
            {
                "url": url,
                "external_id": external_id,
                "text": _post_text(art),
                "created_at": _created_at(art, now),
            }
        )
    return posts[:MAX_POSTS_PER_PAGE]
