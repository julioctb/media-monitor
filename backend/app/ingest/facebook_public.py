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
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from pydantic import BaseModel

from app.ingest.base import RawMention, SourceAdapter
from app.ingest.matching import find_matching_keyword
from app.models.base import MentionSource

log = logging.getLogger("ingest.facebook_public")

FB_PAGE_URL = "https://www.facebook.com/{page_id}/"
# Anchors that only exist once a real post rendered. The generic article div
# appears before the data does, so waiting on it races FB's hydration.
POST_READY_SELECTOR = (
    'a[href*="story_fbid"], a[href*="/posts/"], a[href*="/permalink/"], a[href*="/videos/"]'
)
MAX_POSTS_PER_PAGE = 15  # first screenful is enough for an incremental cycle


class FacebookPageTarget(BaseModel):
    """One monitored public page: id (numeric or slug) + display label."""

    page_id: str
    label: str = ""

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


def to_raw_mentions(
    posts: list[dict[str, Any]],
    page_id: str,
    label: str,
    keywords: Sequence[str],
) -> list[RawMention]:
    """Map parsed post dicts to RawMention (same shape as the Graph adapter)."""
    mentions: list[RawMention] = []
    for post in posts:
        text = post.get("text") or ""
        title = text.split("\n", 1)[0].strip() or None
        mentions.append(
            RawMention(
                source=MentionSource.facebook_page,
                keyword=find_matching_keyword(text, [str(k) for k in keywords]) or "",
                url=post["url"],
                external_id=post.get("external_id"),
                title=title,
                content=text or None,
                # The configured label is the author: the public wall does
                # not always expose the page name per post.
                author=label or None,
                published_at=post.get("created_at"),
                raw={"page_id": page_id, "src": "public_html"},
            )
        )
    return mentions


class FacebookPublicAdapter(SourceAdapter):
    """Scrapes each configured public page's wall with one shared browser."""

    name = "facebook_page"  # logs; the MentionSource enum is already facebook_page

    def __init__(self, pages: Sequence[Any]) -> None:
        # pages: FacebookPageTarget-like objects (page_id + label); kept
        # duck-typed so tests can pass simple stand-ins.
        self._pages = [(getattr(p, "page_id", ""), getattr(p, "label", "")) for p in pages]

    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
        # Imported here so the module (and every test importing it) works
        # without the browsers installed.
        from playwright.sync_api import sync_playwright
        from playwright.sync_api import TimeoutError as PWTimeout

        out: list[RawMention] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            page = browser.new_page(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
                ),
                locale="es-MX",
            )
            try:
                for page_id, label in self._pages:
                    if not page_id:
                        continue
                    try:
                        page.goto(
                            FB_PAGE_URL.format(page_id=page_id),
                            wait_until="domcontentloaded",
                            timeout=25000,
                        )
                        # Wait for a post anchor, not any article shell: FB
                        # renders empty div[role=article] placeholders before
                        # the data hydrates, which caused intermittent
                        # 0-post cycles (the old selector raced the payload).
                        page.wait_for_selector(POST_READY_SELECTOR, timeout=15000)
                        posts = extract_posts(page.content())
                    except PWTimeout as exc:
                        log.warning("facebook public %s: timeout/sin articles: %s", page_id, exc)
                        continue
                    except Exception as exc:  # noqa: BLE001 — una página muerta no frena el ciclo
                        log.warning("facebook public %s fetch failed: %s", page_id, exc)
                        continue
                    if not posts:
                        # One clean retry: a rare FB variant serves the shell
                        # with no anchors at all; the reload usually fixes it.
                        try:
                            page.goto(
                                FB_PAGE_URL.format(page_id=page_id),
                                wait_until="domcontentloaded",
                                timeout=25000,
                            )
                            page.wait_for_selector(POST_READY_SELECTOR, timeout=15000)
                            posts = extract_posts(page.content())
                        except Exception as exc:  # noqa: BLE001
                            log.warning("facebook public %s: retry failed: %s", page_id, exc)
                    if not posts:
                        log.warning("facebook public %s: 0 articles (login wall?)", page_id)
                    out.extend(to_raw_mentions(posts, page_id, label, [str(k) for k in keywords]))
            finally:
                browser.close()
        return out
