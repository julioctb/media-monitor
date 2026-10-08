"""Facebook Page posts ingest via the Meta Graph API.

Scope: pages the client owns or manages. Each FB_PAGES entry carries that
page's own access token (pages_read_engagement); third-party pages need
the one-time Page Public Content Access app review before this same
adapter picks them up.

    GET https://graph.facebook.com/{version}/{page-id}/posts
        ?fields=id,message,created_time,from{name},permalink_url
        &limit=100&access_token=<page token>

Pages are polled sequentially with a single request per page per cycle.
Graph caps feed reads at 100 posts per request and the worker polls every
INGEST_INTERVAL_MIN minutes, so there is deliberately no client-side rate
limiting (unlike the X provider): a handful of pages stays orders of
magnitude below the per-page throttles.

The keyword on each raw mention is a best-effort match done here so the
pipeline's preferred-keyword path can hit; the pipeline re-validates the
match against the full active set and may reassign it, as for any source.
"""

import logging
from collections.abc import Sequence
from datetime import datetime, timezone

import httpx
from pydantic import BaseModel

from app.ingest.base import RawMention, SourceAdapter
from app.ingest.matching import find_matching_keyword
from app.models.base import MentionSource

log = logging.getLogger("ingest.facebook_page")

GRAPH_API_BASE_URL = "https://graph.facebook.com"
# Nested fields use the braces syntax: the dotted form (from.name) is a
# parser syntax error on the Graph field grammar (verified on v26.0).
POST_FIELDS = "id,message,created_time,from{name},permalink_url"
PAGE_POSTS_LIMIT = 100  # Graph's per-request maximum for feed reads
_TIMEOUT_S = 20.0

# Latest stable Graph API version (changelog checked 2026-10-08: v26.0
# released 2026-07-29; the v21.0 fallback pin expires 2027-01-21).
FB_GRAPH_API_VERSION = "v26.0"


class FacebookPageCredentials(BaseModel):
    """One monitored page: id, page access token, display label."""

    page_id: str
    token: str
    label: str = ""


def _parse_created_time(value: object) -> datetime | None:
    """Graph created_time (e.g. 2026-10-08T14:05:00+0000) as aware UTC."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # Graph timestamps are UTC; a naive value is treated as such.
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_page_posts(
    payload: dict,
    page: FacebookPageCredentials,
    keywords: Sequence[str],
) -> list[RawMention]:
    """Map one /posts payload to raw mentions."""
    mentions: list[RawMention] = []
    for post in payload.get("data") or []:
        post_id = str(post.get("id") or "")
        url = post.get("permalink_url") or (
            f"https://www.facebook.com/{page.page_id}/posts/{post_id}"
            if post_id
            else ""
        )
        if not url:
            continue
        message = post.get("message") or None
        title = None
        if message:
            title = message.split("\n", 1)[0].strip() or None
        from_name = (post.get("from") or {}).get("name")
        text = "\n".join(part for part in (title, message) if part)
        mentions.append(
            RawMention(
                source=MentionSource.facebook_page,
                keyword=find_matching_keyword(text, [str(k) for k in keywords]) or "",
                url=url,
                external_id=post_id or None,
                title=title,
                content=message,
                # The configured label wins; the page name on the post is
                # the fallback.
                author=page.label or from_name,
                published_at=_parse_created_time(post.get("created_time")),
                raw={"id": post_id, "page_id": page.page_id},
            )
        )
    return mentions


class FacebookPageAdapter(SourceAdapter):
    """Polls /posts for every configured page, one request per page."""

    name = "facebook_page"

    def __init__(
        self,
        pages: Sequence[FacebookPageCredentials],
        *,
        graph_version: str = FB_GRAPH_API_VERSION,
        client: httpx.Client | None = None,
    ) -> None:
        self._pages = list(pages)
        self._graph_version = graph_version.strip("/")
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)
        self._owns_client = client is None

    def posts_url(self, page_id: str) -> str:
        return f"{GRAPH_API_BASE_URL}/{self._graph_version}/{page_id}/posts"

    def fetch_page_posts(self, page: FacebookPageCredentials) -> dict:
        """One Graph call: the page's latest posts (first page only)."""
        resp = self._client.get(
            self.posts_url(page.page_id),
            params={
                "fields": POST_FIELDS,
                "limit": PAGE_POSTS_LIMIT,
                "access_token": page.token,
            },
        )
        resp.raise_for_status()
        return resp.json()

    def fetch(self, keywords: Sequence[str]) -> list[RawMention]:
        results: list[RawMention] = []
        try:
            for page in self._pages:
                if not page.page_id or not page.token:
                    log.warning("facebook page skipped: missing page_id or token")
                    continue
                try:
                    payload = self.fetch_page_posts(page)
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("facebook page %s fetch failed: %s", page.page_id, exc)
                    continue
                if not isinstance(payload, dict):
                    log.warning("facebook page %s: unexpected payload", page.page_id)
                    continue
                results.extend(parse_page_posts(payload, page, keywords))
        finally:
            if self._owns_client:
                self._client.close()
        return results
