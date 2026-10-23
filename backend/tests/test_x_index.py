"""X-index adapter tests: Google News RSS scoped to x.com (recorded capture).

Mirrors the GoogleNewsAdapter classes in test_adapters.py, but against the
real site:x.com capture (fixture x_index_buap.xml, 3 items trimmed from the
100-item response of 22/oct/2026) plus the worker wiring contract.
"""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.ingest.x_index import XIndexAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class TestXIndexAdapter:
    def test_fetch_builds_site_scoped_query(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["query"] = request.url.params.get("q")
            return httpx.Response(200, text=_fixture("x_index_buap.xml"))

        adapter = XIndexAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        assert adapter.name == "x_index"
        items = adapter.fetch(["BUAP"])

        assert captured["query"] == '"BUAP" site:x.com'
        assert len(items) == 3

    def test_fetch_appends_when_window_from_watermark(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["query"] = request.url.params.get("q")
            return httpx.Response(200, text=_fixture("x_index_buap.xml"))

        adapter = XIndexAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        since = datetime.now(tz=timezone.utc) - timedelta(days=2)
        adapter.fetch(["BUAP"], since=since)

        # hour-granular window, same formula as google_news
        assert captured["query"] == '"BUAP" site:x.com when:49h'

    def test_mentions_come_as_x_twitter_with_stripped_title(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_fixture("x_index_buap.xml"))

        adapter = XIndexAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        items = adapter.fetch(["BUAP"])

        first = items[0]
        assert first.source.value == "x_twitter"
        assert first.keyword == "BUAP"
        assert first.url.startswith("https://news.google.com/rss/articles/")
        assert first.lang == "es"
        assert first.published_at == datetime(2026, 10, 14, 18, 43, 31, tzinfo=timezone.utc)
        # recorded titles all end with " - X"; the adapter strips the suffix
        raw_titles = [
            line.split("<title>", 1)[1].split("</title>", 1)[0]
            for line in _fixture("x_index_buap.xml").splitlines()
            if "<title>" in line and "Google Noticias" not in line
        ]
        for item, raw in zip(items, raw_titles):
            assert raw.endswith(" - X")
            assert item.title == raw[: -len(" - X")]
        assert first.title is not None
        assert first.title.startswith("La rectora Lilia Cedillo")

    def test_fetch_continues_on_http_error(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.params.get("q"))
            if len(calls) == 1:
                return httpx.Response(500)
            return httpx.Response(200, text=_fixture("x_index_buap.xml"))

        adapter = XIndexAdapter(client=httpx.Client(transport=httpx.MockTransport(handler)))
        items = adapter.fetch(["failing", "BUAP"])
        assert len(items) == 3  # second keyword still parsed

    def test_fetch_respects_max_items(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, text=_fixture("x_index_buap.xml"))

        adapter = XIndexAdapter(
            client=httpx.Client(transport=httpx.MockTransport(handler)), max_items=2
        )
        assert len(adapter.fetch(["BUAP"])) == 2


class TestXIndexWiring:
    def test_build_adapters_includes_x_index_in_free_mode(self) -> None:
        from app import worker
        from app.settings_runtime import EffectiveSettings

        adapters = worker.build_adapters(EffectiveSettings(client_id=1))
        names = [a.name for a in adapters]

        # free mode (default): the index adapter rides next to google_news
        assert names[:2] == ["google_news", "x_index"]
        assert isinstance(adapters[1], XIndexAdapter)
