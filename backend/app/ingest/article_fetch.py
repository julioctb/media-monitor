"""Article content fetcher: turn a mention URL into plain article text.

The ingest adapters only carry titles (Google News emits redirect links,
GDELT snippets are often absent), which starves the LLM enrichment. This
module fetches the real article body:

  1. resolve the final publisher URL (Google News ``/articles/`` links are
     JS redirects now; the target comes from the batchexecute endpoint),
  2. GET it once with a browser-ish User-Agent and a short timeout,
  3. extract the main text with BeautifulSoup, falling back to a regex
     tag-strip when the DOM yields nothing usable.

Every entry point returns ``None`` on ANY failure (timeout, non-200,
paywall/JS-only shell, too-short body) — a fetch must never break an
ingest cycle or a backfill run.

Source registry
---------------
``CONTENT_FETCHERS`` maps every ``MentionSource`` to its fetcher and IS
the extension point: X/Facebook posts already carry their text inline
(passthrough, no fetch), while news_rss / rss_custom / gdelt get the
article fetcher. A future X-thread or FB-comment fetcher plugs in as one
new entry here — no pipeline changes.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from html import unescape as html_unescape
from urllib.parse import quote, urlsplit

import httpx
from bs4 import BeautifulSoup

from app.models.base import MentionSource

log = logging.getLogger("ingest.article_fetch")

#: Browser-ish headers: some Puebla news sites (CloudFront) 403 a bare
#: User-Agent; the full browser-ish set passes.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.5",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

#: Per-request timeout; the ingest cycle must stay snappy.
FETCH_TIMEOUT_S = 8.0

#: Below this the extraction is boilerplate noise, not an article body.
MIN_CONTENT_CHARS = 200

#: Hard cap handed to the LLM enrichment (keeps prompts bounded).
MAX_CONTENT_CHARS = 4000

# Tags whose content is navigation/chrome, never article body.
_STRIP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form", "noscript")


def _clean(text: str) -> str:
    """Normalize whitespace but keep paragraph breaks."""
    lines = [line.strip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line for line in lines if line)).strip()


def _paragraphs(node) -> list[str]:  # noqa: ANN001 - bs4 tag
    return [
        p.get_text(" ", strip=True)
        for p in node.find_all("p")
        if len(p.get_text(" ", strip=True)) > 40
    ]


def _regex_fallback(html: str) -> str:
    """Last-resort tag strip for pages bs4 cannot structure."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return _clean(html_unescape(text))


def extract_article_text(html: str) -> str | None:
    """Main article text from an HTML page; None when too little survives.

    Preference order: <article>/<main> paragraphs, then any paragraph, then
    a bare regex tag-strip (JS-heavy pages still carry the body in text
    nodes sometimes). Anything under MIN_CONTENT_CHARS is treated as a
    paywall/JS shell and dropped.
    """
    if not html or not html.strip():
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as exc:  # noqa: BLE001 - malformed HTML must not raise
        log.debug("bs4 parse failed: %s", exc)
        soup = None

    candidates: list[str] = []
    if soup is not None:
        for tag in _STRIP_TAGS:
            for node in soup.find_all(tag):
                node.decompose()
        root = soup.find("article") or soup.find("main") or soup.body or soup
        candidates.append("\n".join(_paragraphs(root)))
        candidates.append("\n".join(_paragraphs(soup)))
    candidates.append(_regex_fallback(html))

    for text in candidates:
        text = _clean(text or "")
        if len(text) >= MIN_CONTENT_CHARS:
            return text[:MAX_CONTENT_CHARS]
    return None


def _is_google_news(url: str) -> bool:
    """Google News /rss/articles/ links: JS redirects, resolved via batchexecute."""
    parts = urlsplit(url)
    return "news.google" in parts.netloc and parts.path.startswith("/rss/articles")


def _resolve_google_news_redirect(url: str, client: httpx.Client) -> str | None:
    """Final publisher URL behind a Google News redirect, or None.

    The /rss/articles/ pages are c-wiz shells; the target comes from the
    batchexecute endpoint keyed by the article id. The request needs the
    ``data-n-a-sg``/``data-n-a-ts`` tokens embedded in the article page
    (a bare payload answers HTTP 400) and an URL-encoded ``f.req`` body.
    Any shape drift returns None — the caller falls back to fetching the
    redirect URL itself.
    """
    article_id = url.split("/articles/", 1)[-1].split("?")[0]
    if not article_id:
        return None
    page_url = f"https://news.google.com/rss/articles/{article_id}?hl=es&gl=MX&ceid=MX:es"
    html = _fetch_page(page_url, client)
    if not html:
        return None
    sg = re.search(r'data-n-a-sg="([^"]+)"', html)
    ts = re.search(r'data-n-a-ts="([^"]+)"', html)
    if not (sg and ts):
        return None
    inner = [
        "garturlreq",
        [
            ["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1, None, None,
             None, None, None, 0, 1],
            "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0,
        ],
        article_id,
        int(ts.group(1)),
        sg.group(1),
    ]
    freq = quote(
        json.dumps(
            [[["Fbv4je", json.dumps(inner, separators=(",", ":")), None, "0"]]],
            separators=(",", ":"),
        )
    )
    try:
        resp = client.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            content=f"f.req={freq}",
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
        )
        body = resp.text
    except httpx.HTTPError as exc:
        log.debug("google news batchexecute failed: %s", exc)
        return None
    return _publisher_url_from_batchexecute(body)


def _fetch_page(url: str, client: httpx.Client) -> str | None:
    """GET with the browser-ish header set; body text or None on failure."""
    try:
        resp = client.get(url, headers=BROWSER_HEADERS, follow_redirects=True)
        if resp.status_code != 200:
            log.debug("fetch %s -> HTTP %d", url, resp.status_code)
            return None
        return resp.text
    except httpx.HTTPError as exc:
        log.debug("fetch %s failed: %s", url, exc)
        return None


def resolve_publisher_url(url: str, client: httpx.Client | None = None) -> str:
    """Canonical publisher URL for dedupe; passthrough for non-Google-News.

    Google News `/rss/articles/` links are per-reader redirect URLs: the same
    article ingested via news_rss and rss_custom hashes differently and lands
    twice. Resolving to the publisher URL (same batchexchange trick the content
    fetch uses) makes both paths collide on one url_hash. Any failure returns
    the input untouched — dedupe must never break ingest.
    """
    if not url or not _is_google_news(url):
        return url
    own_client = client is None
    http = client or httpx.Client(timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    try:
        return _resolve_google_news_redirect(url, http) or url
    except Exception as exc:  # noqa: BLE001 - canonicalization is best-effort
        log.debug("publisher url resolution failed for %s: %s", url, exc)
        return url
    finally:
        if own_client:
            http.close()


#: Meta tags carrying the author byline, in preference order.
_AUTHOR_META_SELECTORS = (
    ("meta", {"name": "author"}),
    ("meta", {"property": "article:author"}),
    ("meta", {"name": "twitter:creator"}),
)


def extract_author(html: str) -> str | None:
    """Byline from article HTML meta tags; None when the page has none.

    Feed bylines are preferred upstream (curated); this covers Google News
    and scraper paths where the RSS carries no author at all.
    """
    if not html or not html.strip():
        return None
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:  # noqa: BLE001 - malformed HTML must not raise
        return None
    for tag, attrs in _AUTHOR_META_SELECTORS:
        node = soup.find(tag, attrs=attrs)
        if node is None:
            continue
        value = (node.get("content") or "").strip()
        if value and not value.startswith(("http", "www.")):
            return _clean(value)[:120] or None
    return None


@dataclass
class ArticleContent:
    """Result of one article fetch: body text plus byline when present."""

    text: str | None
    author: str | None = None

    def __bool__(self) -> bool:
        return bool(self.text and self.text.strip())


def fetch_article_content(url: str, client: httpx.Client | None = None) -> ArticleContent:
    """Article body AND author for a mention URL; empty on ANY failure.

    Google News redirect links are resolved to the publisher URL first
    (batchexecute; a failed resolution just fetches the redirect page).
    Never raises: timeouts, non-200s and extraction misses all return
    empty fields so a fetch can never break an ingest cycle or backfill.
    """
    if not url or not url.strip():
        return ArticleContent(None)
    own_client = client is None
    http = client or httpx.Client(timeout=FETCH_TIMEOUT_S, follow_redirects=True)
    try:
        target = url
        if _is_google_news(url):
            resolved = _resolve_google_news_redirect(url, http)
            if resolved:
                target = resolved
        html = _fetch_page(target, http)
        if html is None and target != url:
            # Resolver picked a dead mirror: one retry on the original.
            html = _fetch_page(url, http)
        if not html:
            return ArticleContent(None)
        return ArticleContent(
            text=extract_article_text(html),
            author=extract_author(html),
        )
    except Exception as exc:  # noqa: BLE001 - a fetch must never raise
        log.warning("article fetch failed for %s: %s", url, exc)
        return ArticleContent(None)
    finally:
        if own_client:
            http.close()


def fetch_article(url: str, client: httpx.Client | None = None) -> str | None:
    """Article body only; see fetch_article_content for the author too."""
    return fetch_article_content(url, client).text


def _fetch_mention_content(url: str) -> ArticleContent | None:
    """Registry-shaped wrapper: ArticleContent, exceptions contained."""
    try:
        return fetch_article_content(url)
    except Exception as exc:  # noqa: BLE001 - belt and braces for the registry
        log.warning("content fetch failed for %s: %s", url, exc)
        return None


#: MentionSource -> content fetcher. x_twitter/facebook_page carry their
#: text inline (passthrough: no fetch); news sources get the article
#: fetcher. This mapping IS the extension point for future fetchers
#: (X threads, FB comments) — add an entry, no pipeline changes.
CONTENT_FETCHERS: dict[MentionSource, Callable[[str], ArticleContent | None] | None] = {
    MentionSource.news_rss: _fetch_mention_content,
    MentionSource.gdelt: _fetch_mention_content,
    MentionSource.rss_custom: _fetch_mention_content,
    # Scraper hits are article URLs: fetch their body like any news source.
    MentionSource.scraper: _fetch_mention_content,
    MentionSource.x_twitter: None,
    MentionSource.facebook_page: None,
}


def fetcher_for(source: MentionSource) -> Callable[[str], ArticleContent | None] | None:
    """The content fetcher for a source, or None when inline/passthrough."""
    return CONTENT_FETCHERS.get(source)



def _collect_urls(node: object, out: list[str], depth: int = 4) -> None:
    """Recursively gather http(s) strings from nested batchexecute arrays.

    The payload nests JSON-inside-strings several levels deep; rather than
    pinning one brittle path we walk everything up to ``depth`` levels and
    also re-parse embedded JSON strings (the ``garturlres`` blob).
    """
    if depth < 0:
        return
    if isinstance(node, str):
        if node.startswith(("http://", "https://")):
            if "news.google" not in node:  # skip google's own echoes
                out.append(node)
            return
        if node.startswith(("[", "{")):
            try:
                _collect_urls(json.loads(node), out, depth - 1)
            except json.JSONDecodeError:
                pass
        return
    if isinstance(node, dict):
        for value in node.values():
            _collect_urls(value, out, depth - 1)
    elif isinstance(node, list):
        for item in node:
            _collect_urls(item, out, depth - 1)


def _publisher_url_from_batchexecute(body: str) -> str | None:
    """The garturlres target inside a batchexecute body; None on drift."""
    if not body.startswith(")]}'"):
        return None
    try:
        data = json.loads(body.lstrip(")]}' \n\t\r"))
    except json.JSONDecodeError as exc:
        log.debug("batchexecute shape drift: %s", exc)
        return None
    urls: list[str] = []
    _collect_urls(data, urls)
    return urls[0] if urls else None
