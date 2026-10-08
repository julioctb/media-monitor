"""X/Twitter provider adapter tests against a recorded-style fixture payload."""

import json
from pathlib import Path

import httpx
import pytest

from app.ingest.twitter_x import (
    COST_PER_1K_TWEETS,
    CostTracker,
    TwitterApiIoProvider,
    build_x_query,
    parse_twitter_payload,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _payload() -> dict:
    return json.loads((FIXTURES / "twitter_advanced_search.json").read_text(encoding="utf-8"))


class TestBuildXQuery:
    def test_quotes_keyword_with_langs_no_retweets(self) -> None:
        assert build_x_query("BUAP") == '"BUAP" (lang:es OR lang:en) -is:retweet'


class TestParsePayload:
    def test_maps_tweets_to_raw_mentions(self) -> None:
        mentions, cursor = parse_twitter_payload(_payload(), "BUAP")
        assert len(mentions) == 2
        first = mentions[0]
        assert first.source.value == "x_twitter"
        assert first.keyword == "BUAP"
        assert first.url == "https://x.com/reportebuap/status/1844000000000000001"
        assert first.external_id == "1844000000000000001"
        assert first.author == "reportebuap"
        assert first.lang == "es"
        assert first.content is not None and "BUAP" in first.content
        assert first.published_at is not None and first.published_at.year == 2026
        assert first.reach == 45  # likes + retweets
        assert cursor == "next-cursor-token"

    def test_builds_url_when_missing(self) -> None:
        payload = {"tweets": [{"id": "42", "text": "hola", "author": {"userName": "alguien"}}]}
        mentions, _ = parse_twitter_payload(payload, "BUAP")
        assert mentions[0].url == "https://x.com/alguien/status/42"

    def test_skips_tweet_without_id_or_url(self) -> None:
        payload = {"tweets": [{"text": "sin id"}]}
        mentions, _ = parse_twitter_payload(payload, "BUAP")
        assert mentions == []


class TestTwitterApiIoProvider:
    def _provider(self, handler, **kwargs) -> TwitterApiIoProvider:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return TwitterApiIoProvider(api_key="test-key", client=client, **kwargs)

    def test_search_sends_bearer_and_query(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("Authorization")
            captured["url"] = str(request.url)
            return httpx.Response(200, json=_payload())

        provider = self._provider(handler)
        payload = provider.search('"BUAP" (lang:es OR lang:en) -is:retweet')
        assert captured["auth"] == "Bearer test-key"
        assert "/twitter/tweet/advanced_search" in captured["url"]
        assert "query=" in captured["url"]
        assert len(payload["tweets"]) == 2

    def test_base_url_configurable(self) -> None:
        provider = self._provider(lambda req: httpx.Response(200, json=_payload()))
        assert provider.search_url == "https://api.twitterapi.io/twitter/tweet/advanced_search"
        provider2 = self._provider(
            lambda req: httpx.Response(200, json=_payload()), base_url="https://api.alt-provider.io/v1/"
        )
        assert provider2.search_url == "https://api.alt-provider.io/v1/twitter/tweet/advanced_search"

    def test_rate_limit_skips_when_exhausted(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json=_payload())

        provider = self._provider(handler, rate_per_minute=1)
        first = provider.search("q1")
        assert len(first["tweets"]) == 2 and len(calls) == 1
        second = provider.search("q2")  # bucket empty -> skipped
        assert second == {} and len(calls) == 1

    def test_cost_tracker_logs_and_accumulates(self, caplog) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload())

        provider = self._provider(handler, rate_per_minute=100)
        with caplog.at_level("INFO", logger="ingest.twitter_x"):
            provider.search('"BUAP" (lang:es OR lang:en) -is:retweet')

        tracker = provider.cost_tracker
        assert tracker.total_requests == 1
        assert tracker.total_tweets == 2
        assert tracker.total_cost_usd == pytest.approx(2 / 1000 * COST_PER_1K_TWEETS)

        json_lines = [
            r.getMessage() for r in caplog.records if r.getMessage().startswith("{")
        ]
        assert any('"event": "x_provider_cost"' in line for line in json_lines)
        parsed = json.loads(json_lines[0])
        assert parsed["tweets"] == 2
        assert parsed["cost_usd"] == pytest.approx(2 / 1000 * COST_PER_1K_TWEETS)

    def test_fetch_per_keyword_and_http_error_resilience(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            q = request.url.params.get("query") or ""
            calls.append(q)
            if "failing" in q:
                return httpx.Response(502)
            return httpx.Response(200, json=_payload())

        provider = self._provider(handler, rate_per_minute=100)
        items = provider.fetch(["failing", "BUAP"])
        assert len(calls) == 2
        assert len(items) == 2  # only BUAP keyword produced items


class TestCostTracker:
    def test_record_math(self) -> None:
        tracker = CostTracker(cost_per_1k=0.15)
        cost = tracker.record(query="q", tweets=1000, duration_s=0.5)
        assert cost == pytest.approx(0.15)
        tracker.record(query="q2", tweets=500, duration_s=0.2)
        assert tracker.total_cost_usd == pytest.approx(0.225)
        assert tracker.total_tweets == 1500
