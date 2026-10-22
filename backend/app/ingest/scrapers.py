"""Scrapers for client sites without RSS (source ``scraper``).

Each registry entry names a site, its homepage(s) and a parser that turns
the served HTML into ``(absolute_url, title)`` article links. Only real
slug paths (>= 2 segments) count; nav, category indexes and static assets
are excluded. Items are keyword-matched best-effort here, like feeds.py;
the pipeline re-validates against the active set. A broken site logs and
is skipped — one bad homepage must never stall the cycle.
"""

import logging
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit

import httpx
from bs4 import BeautifulSoup, Tag

from app.ingest.base import RawMention, SourceAdapter
from app.ingest.matching import find_matching_keyword
from app.models.base import MentionSource

log = logging.getLogger("ingest.scrapers")

_USER_AGENT = "media-monitor/0.1"
_TIMEOUT_S = 20.0
_MAX_PER_PAGE = 100

#: First path segments that are navigation/index/static, never articles.
_NON_ARTICLE_SEGMENTS = frozenset(
    {
        "seccion",
        "secciones",
        "autores",
        "autor",
        "tag",
        "tags",
        "category",
        "page",
        "author",
        "archivo",
        "directorio",
        "fonts",
        "images",
        "img",
        "css",
        "js",
        "static",
        "assets",
        "wp-content",
        "wp-json",
        "wp-login",
        "feed",
        "search",
        "newsletter",
    }
)

#: Static suffixes on the last path segment (assets, feeds, downloads).
_STATIC_SUFFIXES = (
    ".css",
    ".js",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".json",
    ".xml",
    ".webp",
    ".woff",
    ".woff2",
    ".pdf",
    ".txt",
)

_TITLE_CLASS_RE = re.compile(r"titulo|texto|title", re.IGNORECASE)


def _anchor_title(anchor: Tag) -> str:
    """Best-effort headline: heading inside the link, else classed text."""
    for heading in anchor.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        text = " ".join(heading.get_text(" ", strip=True).split())
        if text:
            return text
    block = anchor.find(class_=_TITLE_CLASS_RE)
    if block is not None:
        text = " ".join(block.get_text(" ", strip=True).split())
        if text:
            return text
    return " ".join(anchor.get_text(" ", strip=True).split())


def article_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Deduplicated ``(absolute_url, title)`` article pairs from ``html``.

    A link counts as an article when its path has at least two non-empty
    segments (a real slug), the first segment is not a known nav/static
    prefix, and a non-empty title is extractable. Links are resolved
    against ``base_url`` and restricted to its host.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_host = urlsplit(base_url).netloc
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or parts.netloc != base_host:
            continue  # social/profile/asset hosts are not client articles
        segments = [seg for seg in parts.path.split("/") if seg]
        if len(segments) < 2 or segments[0] in _NON_ARTICLE_SEGMENTS:
            continue
        if segments[-1].lower().endswith(_STATIC_SUFFIXES):
            continue
        title = _anchor_title(anchor)
        if not title:
            continue
        url = absolute.split("#", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        links.append((url, title))
    return links


def parse_diario_laredaccion(html: str) -> list[tuple[str, str]]:
    """diariolaredaccion.mx: article links like /<categoria>/<slug>/."""
    return article_links(html, "https://diariolaredaccion.mx/")


def parse_e_consulta(html: str) -> list[tuple[str, str]]:
    """e-consulta.com: article links like /<categoria>/<slug> (often
    HTML-entity-encoded in the markup; the parser unescapes them)."""
    return article_links(html, "https://www.e-consulta.com/")


def parse_elpopular(html: str) -> list[tuple[str, str]]:
    """elpopular.mx: no feed; articles are /<taxo>[/<sub>]/YYYY/MM/DD/<slug>.

    The date triple is the only reliable article/nav discriminator here:
    nav includes /reporteros/<slug> (author pages) and /secciones/<slug>
    (category indexes), while real stories always carry the date path.
    """
    soup = BeautifulSoup(html, "html.parser")
    base_url = "https://elpopular.mx/"
    base_host = urlsplit(base_url).netloc
    links: list[tuple[str, str]] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"].strip()
        if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        absolute = urljoin(base_url, href)
        parts = urlsplit(absolute)
        if parts.scheme not in ("http", "https") or parts.netloc != base_host:
            continue
        segments = [seg for seg in parts.path.split("/") if seg]
        dated = any(
            re.fullmatch(r"\d{4}", segments[i])
            and re.fullmatch(r"\d{2}", segments[i + 1])
            and re.fullmatch(r"\d{2}", segments[i + 2])
            for i in range(len(segments) - 3)
        )
        if not dated:
            continue
        title = _anchor_title(anchor)
        if not title:
            continue
        url = absolute.split("#", 1)[0]
        if url in seen:
            continue
        seen.add(url)
        links.append((url, title))
    return links


_LAREDACCION_BASE_URL = "https://diariolaredaccion.mx"
_E_CONSULTA_BASE_URL = "https://www.e-consulta.com"
_ELPOPULAR_BASE_URL = "https://elpopular.mx"


@dataclass(frozen=True)
class ScraperSpec:
    """One scrapable site: base URL, listing pages, HTML parser."""

    base_url: str
    list_urls: tuple[str, ...]
    parse: Callable[[str], list[tuple[str, str]]]


SCRAPER_REGISTRY: dict[str, ScraperSpec] = {
    "diario_laredaccion": ScraperSpec(
        base_url=_LAREDACCION_BASE_URL,
        list_urls=(f"{_LAREDACCION_BASE_URL}/",),
        parse=parse_diario_laredaccion,
    ),
    "e_consulta": ScraperSpec(
        base_url=_E_CONSULTA_BASE_URL,
        list_urls=(f"{_E_CONSULTA_BASE_URL}/",),
        parse=parse_e_consulta,
    ),
    "elpopular": ScraperSpec(
        base_url=_ELPOPULAR_BASE_URL,
        list_urls=(
            f"{_ELPOPULAR_BASE_URL}/",
            f"{_ELPOPULAR_BASE_URL}/secciones/puebla",
        ),
        parse=parse_elpopular,
    ),
}


class ScrapersAdapter(SourceAdapter):
    """Polls every client-enabled registry scraper, one request per page."""

    name = "scraper"

    def __init__(
        self,
        names: Sequence[str],
        *,
        client: httpx.Client | None = None,
        max_per_page: int = _MAX_PER_PAGE,
    ) -> None:
        self._names = list(names)
        self._client = client or httpx.Client(
            headers={"User-Agent": _USER_AGENT},
            timeout=_TIMEOUT_S,
            follow_redirects=True,
        )
        self._owns_client = client is None
        self._max_per_page = max_per_page

    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
        del since  # homepages are rank-ordered, not date-windowed
        keyword_texts = [str(k) for k in keywords]
        results: list[RawMention] = []
        try:
            for name in self._names:
                spec = SCRAPER_REGISTRY.get(name)
                if spec is None:
                    log.warning("unknown scraper %r: skipped", name)
                    continue
                for list_url in spec.list_urls:
                    html = self._fetch_html(list_url)
                    if html is None:
                        continue
                    pairs = spec.parse(html)
                    if len(pairs) > self._max_per_page:
                        pairs = pairs[: self._max_per_page]
                    log.info("scraper %s: %d links from %s", name, len(pairs), list_url)
                    for url, title in pairs:
                        results.append(
                            RawMention(
                                source=MentionSource.scraper,
                                keyword=find_matching_keyword(title, keyword_texts)
                                or "",
                                url=url,
                                title=title,
                                content=None,
                                published_at=None,
                            )
                        )
        finally:
            if self._owns_client:
                self._client.close()
        return results

    def _fetch_html(self, url: str) -> str | None:
        for attempt in range(2):
            try:
                resp = self._client.get(url)
                resp.raise_for_status()
                return resp.text
            except (httpx.HTTPError, ValueError) as exc:
                # Transient DNS/SSL/redirect hiccups: one quiet retry.
                log.warning("scraper page %s failed (attempt %d): %s", url, attempt + 1, exc)
                time.sleep(1.5)
        return None
