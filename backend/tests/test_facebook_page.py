"""Facebook Pages adapter tests against a recorded-style fixture payload."""

import json
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from pydantic import ValidationError

from app.config import Settings
from app.ingest.facebook_page import (
    FacebookPageCredentials,
    POST_FIELDS,
    FacebookPageAdapter,
    parse_page_posts,
)
from app.ingest.pipeline import run_ingest_cycle
from app.models import MentionSource, Keyword, queries

FIXTURES = Path(__file__).parent / "fixtures"

PAGE = FacebookPageCredentials(page_id="1001", token="page-token", label="BUAP Oficial")

GROUP = FacebookPageCredentials(
    page_id="1090003732034388", token="group-token", label="Grupo BUAP", kind="group"
)


def _payload() -> dict:
    return json.loads(
        (FIXTURES / "facebook_page_posts.json").read_text(encoding="utf-8")
    )


class TestParsePagePosts:
    def test_maps_posts_to_raw_mentions(self) -> None:
        mentions = parse_page_posts(_payload(), PAGE, ["BUAP"])
        assert len(mentions) == 2
        first = mentions[0]
        assert first.source.value == "facebook_page"
        assert first.keyword == "BUAP"
        assert first.external_id == "1001_20261008_1"
        assert first.url == "https://www.facebook.com/1001/posts/20261008_1"
        assert first.title == "La BUAP abrió su convocatoria de becas de ingeniería 🎓"
        assert first.content is not None and "\n" in first.content
        assert first.author == "BUAP Oficial"  # configured label wins
        assert first.published_at is not None
        assert first.published_at.tzinfo is not None
        assert first.published_at.year == 2026
        assert first.published_at.utcoffset() == timedelta(0)  # Graph UTC
        assert first.raw == {"id": "1001_20261008_1", "page_id": "1001"}

    def test_label_empty_falls_back_to_from_name(self) -> None:
        page = FacebookPageCredentials(page_id="1001", token="t")
        mentions = parse_page_posts(_payload(), page, [])
        assert mentions[0].author == "BUAP Oficial"  # from.name
        assert mentions[1].author is None  # no label, no from on the post

    def test_builds_url_when_permalink_missing(self) -> None:
        payload = {"data": [{"id": "1001_9", "message": "hola"}]}
        (mention,) = parse_page_posts(payload, PAGE, [])
        assert mention.url == "https://www.facebook.com/1001/posts/1001_9"

    def test_title_is_first_line_or_none(self) -> None:
        payload = {"data": [{"id": "1", "message": "primera\nsegunda"}, {"id": "2"}]}
        mentions = parse_page_posts(payload, PAGE, [])
        assert mentions[0].title == "primera"
        assert mentions[1].title is None and mentions[1].content is None

    def test_skips_post_without_id_and_permalink(self) -> None:
        payload = {"data": [{"message": "sin id"}]}
        assert parse_page_posts(payload, PAGE, []) == []

    def test_keyword_empty_when_no_match(self) -> None:
        payload = {"data": [{"id": "1", "message": "nada que ver"}]}
        (mention,) = parse_page_posts(payload, PAGE, ["BUAP"])
        assert mention.keyword == ""

    def test_created_time_edge_cases(self) -> None:
        payload = {
            "data": [
                {"id": "1", "created_time": "2026-10-08T14:05:00"},  # naive
                {"id": "2", "created_time": "not-a-date"},
                {"id": "3"},  # missing
            ]
        }
        mentions = parse_page_posts(payload, PAGE, [])
        assert mentions[0].published_at is not None
        assert mentions[0].published_at.tzinfo is not None  # naive read as UTC
        assert mentions[1].published_at is None
        assert mentions[2].published_at is None

    # --- kind=group: parsing is shared, only the fallback URL branches ---

    def test_group_payload_parses_with_page_rules(self) -> None:
        payload = {
            "data": [
                {
                    "id": "1090003732034388_77",
                    "message": "primera\nsegunda",
                    "from": {"name": "Miembro"},
                }
            ]
        }
        (mention,) = parse_page_posts(payload, GROUP, [])
        assert mention.source.value == "facebook_page"  # enum reused for groups
        assert mention.title == "primera"  # first line
        assert mention.content == "primera\nsegunda"
        assert mention.author == "Grupo BUAP"  # label wins over from
        assert mention.external_id == "1090003732034388_77"
        assert mention.url == "https://www.facebook.com/groups/1090003732034388/posts/77"

    def test_group_fallback_url_suffix_after_first_underscore(self) -> None:
        payload = {"data": [{"id": "1090003732034388_777", "message": "hola"}]}
        (mention,) = parse_page_posts(payload, GROUP, [])
        assert mention.url == "https://www.facebook.com/groups/1090003732034388/posts/777"

    def test_group_fallback_url_without_underscore_keeps_full_id(self) -> None:
        payload = {"data": [{"id": "987", "message": "hola"}]}
        (mention,) = parse_page_posts(payload, GROUP, [])
        assert mention.url == "https://www.facebook.com/groups/1090003732034388/posts/987"


class TestFacebookPageAdapter:
    def _adapter(self, handler, **kwargs) -> FacebookPageAdapter:
        client = httpx.Client(transport=httpx.MockTransport(handler))
        return FacebookPageAdapter([PAGE], client=client, **kwargs)

    def test_posts_url_query_params_and_parsing(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json=_payload())

        items = self._adapter(handler).fetch(["BUAP"])
        assert captured["url"].startswith(
            "https://graph.facebook.com/v26.0/1001/posts"
        )
        assert captured["params"]["fields"] == POST_FIELDS
        assert "from{name}" in captured["params"]["fields"]
        assert captured["params"]["limit"] == "100"
        assert captured["params"]["access_token"] == "page-token"
        assert len(items) == 2

    def test_graph_version_override(self) -> None:
        adapter = self._adapter(
            lambda request: httpx.Response(200, json={"data": []}),
            graph_version="v25.0",
        )
        assert adapter.posts_url("1001") == "https://graph.facebook.com/v25.0/1001/posts"

    def test_http_error_on_one_page_skips_only_that_page(self) -> None:
        page_b = FacebookPageCredentials(page_id="2002", token="t2", label="B")
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            if "/2002/" in request.url.path:
                return httpx.Response(500)
            return httpx.Response(200, json=_payload())

        adapter = FacebookPageAdapter(
            [PAGE, page_b], client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        items = adapter.fetch(["BUAP"])
        assert len(calls) == 2  # both pages attempted
        assert len(items) == 2  # only the healthy page produced items

    def test_pages_without_token_or_id_are_skipped(self) -> None:
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)
            return httpx.Response(200, json=_payload())

        empty = FacebookPageCredentials(page_id="", token="")
        adapter = FacebookPageAdapter(
            [empty], client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        assert adapter.fetch(["BUAP"]) == []
        assert calls == []

    def test_non_dict_payload_is_ignored(self) -> None:
        adapter = self._adapter(lambda request: httpx.Response(200, json=[1, 2]))
        assert adapter.fetch(["BUAP"]) == []

    def test_posts_url_group_branch(self) -> None:
        adapter = self._adapter(lambda request: httpx.Response(200, json={"data": []}))
        assert adapter.posts_url("1090003732034388", kind="group") == (
            "https://graph.facebook.com/v26.0/groups/1090003732034388/feed"
        )

    def test_group_kind_fetches_groups_feed_endpoint(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["params"] = dict(request.url.params)
            return httpx.Response(200, json=_payload())

        adapter = FacebookPageAdapter(
            [GROUP], client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        items = adapter.fetch(["BUAP"])
        assert captured["url"].startswith(
            "https://graph.facebook.com/v26.0/groups/1090003732034388/feed"
        )
        assert captured["params"]["fields"] == POST_FIELDS
        assert captured["params"]["limit"] == "100"
        assert captured["params"]["access_token"] == "group-token"
        assert len(items) == 2  # same parse path as pages

    def test_mixed_pages_and_groups_hit_their_own_endpoints(self) -> None:
        paths = []

        def handler(request: httpx.Request) -> httpx.Response:
            paths.append(request.url.path)
            return httpx.Response(200, json={"data": []})

        adapter = FacebookPageAdapter(
            [PAGE, GROUP], client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        assert adapter.fetch(["BUAP"]) == []
        assert paths == [
            "/v26.0/1001/posts",
            "/v26.0/groups/1090003732034388/feed",
        ]


class TestFacebookPagesSettings:
    def test_unset_env_means_disabled(self, monkeypatch) -> None:
        monkeypatch.delenv("FB_PAGES", raising=False)
        assert Settings(_env_file=None).fb_pages == []

    def test_empty_env_means_disabled(self, monkeypatch) -> None:
        monkeypatch.setenv("FB_PAGES", "")
        assert Settings(_env_file=None).fb_pages == []

    def test_json_env_parsed_into_targets(self, monkeypatch) -> None:
        # Legacy rows carry token/kind extras: pydantic ignores them.
        monkeypatch.setenv(
            "FB_PAGES", '[{"page_id": "1001", "token": "t", "label": "L"}]'
        )
        pages = Settings(_env_file=None).fb_pages
        assert pages[0].page_id == "1001"
        assert pages[0].label == "L"

    def test_label_optional_and_bad_json_raises(self, monkeypatch) -> None:
        monkeypatch.setenv("FB_PAGES", '[{"page_id": "1001", "token": "t"}]')
        assert Settings(_env_file=None).fb_pages[0].label == ""
        monkeypatch.setenv("FB_PAGES", "nope")
        with pytest.raises(ValidationError):
            Settings(_env_file=None)


class TestPipelineIntegration:
    def test_facebook_mention_flows_through_pipeline(self, session) -> None:
        client = queries.get_or_create_client(session, "default")
        keyword = Keyword(client_id=client.id, text="BUAP", language="es", is_active=True)
        session.add(keyword)
        session.commit()

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_payload())

        adapter = FacebookPageAdapter(
            [PAGE], client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        stats = run_ingest_cycle(
            session,
            client_id=client.id,
            keywords=[keyword],
            adapters=[adapter],
            sentiment_analyzer=None,
        )
        # Post 1 mentions BUAP; post 2 carries no tracked keyword.
        assert stats == {"facebook_page": 1}

        mentions = queries.list_mentions(session, client.id)
        assert len(mentions) == 1
        row = mentions[0]
        assert row.source is MentionSource.facebook_page
        assert row.keyword_id == keyword.id
        assert row.external_id == "1001_20261008_1"
        assert row.sentiment is None  # no analyzer -> NULL, backfillable
