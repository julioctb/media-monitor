"""Adapter tests against recorded fixture payloads (no live network).

Fixtures live in backend/tests/fixtures/. httpx.MockTransport injects the
recorded bytes so adapter parsing logic is exercised for real.
"""

from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.ingest.gdelt import GdeltAdapter, build_gdelt_query, parse_gdelt_payload
from app.ingest.google_news import GoogleNewsAdapter, parse_google_rss

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestGoogleNewsAdapter:
    def test_parses_fixture_items(self) -> None:
        items = parse_google_rss(_fixture("google_news_buap.xml"), "BUAP")
        assert len(items) == 3
        first = items[0]
        assert first.source.value == "news_rss"
        assert first.keyword == "BUAP"
        assert first.url.startswith("https://news.google.com/rss/articles/")
        assert first.title == "La BUAP anunció nuevos laboratorios"
        assert first.lang == "es"
        assert first.published_at == datetime(2026, 10, 8, 12, 0, tzinfo=timezone.utc)

    def test_skips_entries_without_link(self) -> None:
        items = parse_google_rss(_fixture("google_news_empty_link.xml"), "BUAP")
        assert items == []

    def test_fetch_via_mock_transport(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(200, text=_fixture("google_news_buap.xml"))

        adapter = GoogleNewsAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        items = adapter.fetch(["BUAP"])
        assert len(items) == 3
        assert "news.google.com/rss/search" in captured["url"]
        assert "hl=es" in captured["url"] and "gl=MX" in captured["url"]
        assert "ceid=MX%3AMES" in captured["url"] or "ceid=MX%3Aes" in captured["url"]

    def test_fetch_continues_on_http_error(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.params.get("q"))
            if len(calls) == 1:
                return httpx.Response(500)
            return httpx.Response(200, text=_fixture("google_news_buap.xml"))

        adapter = GoogleNewsAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        items = adapter.fetch(["failing", "BUAP"])
        assert len(items) == 3  # second keyword still parsed


class TestGdeltAdapter:
    def test_parses_fixture_payload(self) -> None:
        import json

        payload = json.loads(_fixture("gdelt_buap.json"))
        items = parse_gdelt_payload(payload, "BUAP")
        assert len(items) == 2
        first = items[0]
        assert first.source.value == "gdelt"
        assert first.url == "https://www.e-consulta.com/nota/2026-10-08/buap-convenio"
        assert first.title == "BUAP firma convenio internacional"
        assert first.published_at == datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc)
        assert first.raw["domain"] == "e-consulta.com"

    def test_seendate_bad_format_is_tolerated(self) -> None:
        items = parse_gdelt_payload({"articles": [{"url": "https://x.com/1", "seendate": "garbage"}]}, "BUAP")
        assert items[0].published_at is None

    def test_fetch_via_mock_transport(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["query"] = request.url.params.get("query")
            return httpx.Response(200, text=_fixture("gdelt_buap.json"))

        adapter = GdeltAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        items = adapter.fetch(["BUAP"])
        assert len(items) == 2
        assert "api.gdeltproject.org/api/v2/doc/doc" in captured["url"]
        assert 'sourcelang:spanish OR sourcelang:english' in captured["query"]
        assert "mode=artlist" in captured["url"] and "format=json" in captured["url"]

    def test_build_gdelt_query(self) -> None:
        assert build_gdelt_query("BUAP") == '"BUAP" (sourcelang:spanish OR sourcelang:english)'
