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
from html import unescape as html_unescape
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup

from app.models.base import MentionSource

log = logging.getLogger("ingest.article_fetch")

#: Browser-ish User-Agent: some Puebla news sites 403 plain clients.
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

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

    The /rss/articles/ pages are c-wiz shells; the target URL comes from
    the batchexecute endpoint keyed by the article id (the ``garturlres``
    entry inside the nested JSON blob). Any shape drift returns None —
    the caller falls back to fetching the redirect URL itself.
    """
    article_id = url.split("/articles/", 1)[-1].split("?")[0]
    if not article_id:
        return None
    payload = json.dumps([[None, [[None, article_id]]]], separators=(",", ":"))
    try:
        resp = client.post(
            "https://news.google.com/_/DotsSplashUi/data/batchexecute",
            data={"f.req": json.dumps([["Fbv4je", payload, None, "generic"]])},
        )
        body = resp.text
    except httpx.HTTPError as exc:
        log.debug("google news batchexecute failed: %s", exc)
        return None
    return _publisher_url_from_batchexecute(body)


def _fetch_page(url: str, client: httpx.Client) -> str | None:
    """GET with the browser UA; body text or None on any failure."""
    try:
        resp = client.get(url, headers={"User-Agent": USER_AGENT}, follow_redirects=True)
        if resp.status_code != 200:
            log.debug("fetch %s -> HTTP %d", url, resp.status_code)
            return None
        return resp.text
    except httpx.HTTPError as exc:
        log.debug("fetch %s failed: %s", url, exc)
        return None


def fetch_article(url: str, client: httpx.Client | None = None) -> str | None:
    """Article body for a mention URL; None on ANY failure.

    Google News redirect links are resolved to the publisher URL first
    (batchexecute; a failed resolution just fetches the redirect page).
    Never raises: timeouts, non-200s and extraction misses all return
    None so a fetch can never break an ingest cycle or backfill.
    """
    if not url or not url.strip():
        return None
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
        return extract_article_text(html) if html else None
    except Exception as exc:  # noqa: BLE001 - a fetch must never raise
        log.warning("article fetch failed for %s: %s", url, exc)
        return None
    finally:
        if own_client:
            http.close()


def _fetch_mention_content(url: str) -> str | None:
    """Registry-shaped wrapper: content or None, exceptions contained."""
    try:
        return fetch_article(url)
    except Exception as exc:  # noqa: BLE001 - belt and braces for the registry
        log.warning("content fetch failed for %s: %s", url, exc)
        return None


#: MentionSource -> content fetcher. x_twitter/facebook_page carry their
#: text inline (passthrough: no fetch); news sources get the article
#: fetcher. This mapping IS the extension point for future fetchers
#: (X threads, FB comments) — add an entry, no pipeline changes.
CONTENT_FETCHERS: dict[MentionSource, Callable[[str], str | None] | None] = {
    MentionSource.news_rss: _fetch_mention_content,
    MentionSource.gdelt: _fetch_mention_content,
    MentionSource.rss_custom: _fetch_mention_content,
    MentionSource.x_twitter: None,
    MentionSource.facebook_page: None,
}


def fetcher_for(source: MentionSource) -> Callable[[str], str | None] | None:
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
