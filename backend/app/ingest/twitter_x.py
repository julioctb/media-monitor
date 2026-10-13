"""X/Twitter ingest via a pluggable third-party provider.

The MVP targets twitterapi.io-compatible providers:
  GET {base_url}/twitter/tweet/advanced_search
      Authorization: Bearer <token>
      ?query=<query>&cursor=<cursor>

X_PROVIDER_BASE_URL is configurable so any compatible provider works. The
adapter adds client-side rate limiting (token bucket) and per-query cost
tracking: every request logs one structured JSON line with the estimated
USD cost ($0.15 per 1,000 tweets read) — no cost table needed for MVP.
"""

import json
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime, timezone

import httpx

from app.ingest.base import RawMention, SourceAdapter
from app.ingest.rate_limit import TokenBucket
from app.models.base import MentionSource

log = logging.getLogger("ingest.twitter_x")

# twitterapi.io pricing: ~$0.15 per 1,000 tweets read.
COST_PER_1K_TWEETS = 0.15
DEFAULT_RATE_PER_MIN = 10.0
_TIMEOUT_S = 20.0


def build_x_query(keyword: str) -> str:
    """Search query for one keyword: ES or EN, no retweets."""
    return f'"{keyword}" (lang:es OR lang:en) -is:retweet'


class XProvider(ABC):
    """Provider-agnostic search interface so alternatives can be plugged in."""

    @abstractmethod
    def search(self, query: str, cursor: str | None = None) -> dict:
        """Return the raw provider payload for one search page."""
        raise NotImplementedError


class CostTracker:
    """Accumulates estimated spend and logs one JSON line per query."""

    def __init__(self, cost_per_1k: float = COST_PER_1K_TWEETS) -> None:
        self.cost_per_1k = cost_per_1k
        self.total_tweets = 0
        self.total_requests = 0
        self.total_cost_usd = 0.0

    def record(self, *, query: str, tweets: int, duration_s: float) -> float:
        cost = tweets / 1000.0 * self.cost_per_1k
        self.total_tweets += tweets
        self.total_requests += 1
        self.total_cost_usd += cost
        log.info(
            json.dumps(
                {
                    "event": "x_provider_cost",
                    "query": query,
                    "tweets": tweets,
                    "cost_usd": round(cost, 6),
                    "total_cost_usd": round(self.total_cost_usd, 6),
                    "duration_s": round(duration_s, 3),
                }
            )
        )
        return cost


def parse_twitter_payload(payload: dict, keyword: str) -> tuple[list[RawMention], str | None]:
    """Map a twitterapi.io advanced_search payload to raw mentions.

    Returns (mentions, next_cursor).
    """
    tweets = payload.get("tweets") or []
    mentions: list[RawMention] = []
    for tw in tweets:
        url = tw.get("url") or (
            f"https://x.com/{tw.get('author', {}).get('userName')}/status/{tw.get('id')}"
            if tw.get("id")
            else ""
        )
        if not url:
            continue
        created = tw.get("createdAt")  # ISO-8601 e.g. 2026-10-08T12:34:56.000Z
        published_at = None
        if isinstance(created, str):
            try:
                published_at = datetime.fromisoformat(created.replace("Z", "+00:00"))
            except ValueError:
                published_at = None
        mentions.append(
            RawMention(
                source=MentionSource.x_twitter,
                keyword=keyword,
                url=url,
                external_id=str(tw.get("id")) if tw.get("id") else None,
                title=None,
                content=tw.get("text") or None,
                author=(tw.get("author") or {}).get("userName"),
                lang=tw.get("lang"),
                published_at=published_at,
                reach=tw.get("likeCount", 0) + tw.get("retweetCount", 0) or None,
                raw={"id": tw.get("id")},
            )
        )
    return mentions, payload.get("cursor") or None


class TwitterApiIoProvider(XProvider, SourceAdapter):
    """twitterapi.io-compatible provider client and ingest adapter.

    One source adapter that is also its own provider transport: fetch()
    runs one search per keyword (single page per cycle keeps cost bounded),
    acquiring a token first so the configured req/min budget is respected.
    """

    name = "x_twitter"

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.twitterapi.io",
        rate_per_minute: float = DEFAULT_RATE_PER_MIN,
        client: httpx.Client | None = None,
        cost_tracker: CostTracker | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._bucket = TokenBucket(rate_per_minute, capacity=max(1.0, rate_per_minute))
        self._client = client or httpx.Client(timeout=_TIMEOUT_S)
        self._owns_client = client is None
        self.cost_tracker = cost_tracker or CostTracker()

    @property
    def search_url(self) -> str:
        return f"{self._base_url}/twitter/tweet/advanced_search"

    def search(self, query: str, cursor: str | None = None) -> dict:
        """One rate-limited GET against the advanced_search endpoint."""
        if not self._bucket.try_acquire():
            log.warning("x provider rate limit hit, skipping query %r", query)
            return {}
        params: dict[str, str] = {"query": query}
        if cursor:
            params["cursor"] = cursor
        started = time.monotonic()
        # Auth is sent per request so injected clients (tests, proxies) are
        # authenticated exactly like the default one.
        resp = self._client.get(
            self.search_url,
            params=params,
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        payload = resp.json()
        tweets = len(payload.get("tweets") or [])
        self.cost_tracker.record(
            query=query, tweets=tweets, duration_s=time.monotonic() - started
        )
        return payload

    def fetch(
        self, keywords: Sequence[str], since: datetime | None = None
    ) -> list[RawMention]:
        results: list[RawMention] = []
        try:
            for keyword in keywords:
                keyword = str(keyword).strip()
                if not keyword:
                    continue
                try:
                    payload = self.search(build_x_query(keyword))
                except (httpx.HTTPError, ValueError) as exc:
                    log.warning("x provider fetch failed for %r: %s", keyword, exc)
                    continue
                if not isinstance(payload, dict):
                    continue
                mentions, _cursor = parse_twitter_payload(payload, keyword)
                results.extend(mentions)
        finally:
            if self._owns_client:
                self._client.close()
        return results
