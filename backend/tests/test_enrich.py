"""Enrichment tests (F2c): LLM client, parsing, event summary.

Fully offline: transport via httpx.MockTransport, event summary on
in-memory SQLite.
"""

import json
from datetime import datetime, timezone

import httpx
import pytest

from app.enrich.llm import LLMEnricher, parse_enrichment
from app.enrich.summary import maybe_summarize_event
from app.models import Client, Event, Mention
from app.models.base import Sentiment

GOOD_PAYLOAD = {
    "summary": "La BUAP inauguró su nuevo edificio.",
    "sentiment": "positive",
    "sentiment_score": 0.9,
    "persons": [
        {
            "name": "La rectora",
            "role": "rectora",
            "org": "BUAP",
            "statement": "Es una obra para todos",
            "stance": "a favor",
        }
    ],
    "topics": ["educacion", "infraestructura"],
    "political": "political",
    "unexpected": "ignored",
}


def _ok_handler(calls: list[dict], content: str | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(json.loads(request.content))
        body = content if content is not None else json.dumps(GOOD_PAYLOAD)
        return httpx.Response(
            200, json={"choices": [{"message": {"content": body}}]}
        )

    return handler


def _enricher(handler, **kwargs) -> LLMEnricher:
    kwargs.setdefault("api_key", "sk-test")
    kwargs.setdefault("client", httpx.Client(transport=httpx.MockTransport(handler)))
    return LLMEnricher(**kwargs)


class TestEnrichmentResult:
    def test_parses_valid_payload(self) -> None:
        result = parse_enrichment(json.dumps(GOOD_PAYLOAD))
        assert result.summary == "La BUAP inauguró su nuevo edificio."
        assert result.sentiment is Sentiment.positive
        assert result.sentiment_score == 0.9
        assert result.persons[0].name == "La rectora"
        assert result.persons[0].stance == "a favor"
        assert result.topics == ["educacion", "infraestructura"]
        assert result.political == "political"

    def test_political_absent_or_invalid_degrades_to_none(self) -> None:
        absent = dict(GOOD_PAYLOAD)
        absent.pop("political")
        result = parse_enrichment(json.dumps(absent))
        assert result.political is None

        loose = dict(GOOD_PAYLOAD, political="  Not_Political ")
        assert parse_enrichment(json.dumps(loose)).political == "not_political"

        invalid = dict(GOOD_PAYLOAD, political="sortof")
        assert parse_enrichment(json.dumps(invalid)).political is None

        nonstr = dict(GOOD_PAYLOAD, political=1)
        assert parse_enrichment(json.dumps(nonstr)).political is None

    def test_accepts_code_fenced_json(self) -> None:
        fenced = "```json\n" + json.dumps(GOOD_PAYLOAD) + "\n```"
        assert parse_enrichment(fenced).sentiment is Sentiment.positive

    def test_coerces_loose_but_valid_types(self) -> None:
        loose = dict(GOOD_PAYLOAD, sentiment=" Positive ", sentiment_score="0.5")
        result = parse_enrichment(json.dumps(loose))
        assert result.sentiment is Sentiment.positive
        assert result.sentiment_score == 0.5

    def test_rejects_broken_json(self) -> None:
        with pytest.raises(ValueError):
            parse_enrichment("esto no es json")

    def test_rejects_non_object(self) -> None:
        with pytest.raises(ValueError):
            parse_enrichment("[1, 2, 3]")

    def test_rejects_empty_summary_and_bad_score(self) -> None:
        with pytest.raises(Exception):  # noqa: B017 - pydantic ValidationError
            parse_enrichment(json.dumps(dict(GOOD_PAYLOAD, summary="  ")))
        with pytest.raises(Exception):  # noqa: B017
            parse_enrichment(json.dumps(dict(GOOD_PAYLOAD, sentiment_score=7)))

    def test_drops_nameless_person_entries(self) -> None:
        payload = dict(
            GOOD_PAYLOAD,
            persons=[
                {"name": None, "role": "rectora"},
                {"name": "  ", "org": "BUAP"},
                {"name": " Lilia Cedillo ", "role": None},
                "not-a-person",
            ],
        )
        result = parse_enrichment(json.dumps(payload))
        assert [p.name for p in result.persons] == ["Lilia Cedillo"]
        assert result.persons[0].role is None


class TestLLMEnricher:
    def test_request_shape_temperature0_json_mode_truncation(self) -> None:
        calls: list[dict] = []
        enricher = _enricher(_ok_handler(calls))
        long_text = "palabra " * 500  # 3500 chars -> truncated
        result = enricher.enrich(long_text, "es")
        assert result is not None
        body = calls[0]
        assert body["temperature"] == 0
        assert body["response_format"] == {"type": "json_object"}
        assert body["model"] == "gpt-4o-mini"
        user_content = body["messages"][1]["content"]
        assert long_text.split()[0] in user_content
        assert len(user_content) < 2000  # article clipped at 1500 + prompt

    def test_retries_then_returns_result(self) -> None:
        calls: list[dict] = []
        responses = ["no json yet", json.dumps(GOOD_PAYLOAD)]

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": responses[len(calls) - 1]}}]},
            )

        enricher = _enricher(handler)
        result = enricher.enrich("texto")
        assert result is not None and len(calls) == 2

    def test_transport_failure_returns_none(self) -> None:
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append({})
            raise httpx.ConnectError("boom")

        enricher = _enricher(handler, attempts=2, backoff_s=0)
        assert enricher.enrich("texto") is None
        assert len(calls) == 2  # attempts honored, exception contained

    def test_broken_json_retried_then_none(self) -> None:
        calls: list[dict] = []
        enricher = _enricher(_ok_handler(calls, content="no soy json"))
        assert enricher.enrich("texto") is None
        assert len(calls) == 2

    def test_empty_text_short_circuits(self) -> None:
        calls: list[dict] = []
        enricher = _enricher(_ok_handler(calls))
        assert enricher.enrich("   ") is None
        assert calls == []

    def test_complete_none_content_retried_then_value(self) -> None:
        # Local servers return content:null under load; str(None) -> "None"
        # used to leak as the answer/digest payload. Now retried like a 5xx.
        calls: list[dict] = []
        responses: list[str | None] = [None, json.dumps(GOOD_PAYLOAD)]

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": responses[len(calls) - 1]}}]},
            )

        enricher = _enricher(handler, attempts=2, backoff_s=0)
        assert enricher.complete("s", "u", json_mode=True) == json.dumps(GOOD_PAYLOAD)
        assert len(calls) == 2

    def test_complete_all_none_content_returns_none(self) -> None:
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append({})
            return httpx.Response(200, json={"choices": [{"message": {"content": None}}]})

        enricher = _enricher(handler, attempts=2, backoff_s=0)
        assert enricher.complete("s", "u") is None
        assert len(calls) == 2

    def test_requires_api_key(self) -> None:
        with pytest.raises(ValueError):
            LLMEnricher(api_key="")


class FakeSummarizer:
    """Records summarize() inputs; returns a fixed text or None."""

    def __init__(self, text: str | None = "RESUMEN") -> None:
        self.text = text
        self.inputs: list[str] | None = None

    def summarize(self, inputs: list[str]) -> str | None:
        self.inputs = list(inputs)
        return self.text


class TestEventSummary:
    def _seed(self, session, rows):
        from app.models import MentionSource, make_url_hash

        client = Client(name="c")
        session.add(client)
        session.commit()
        now = datetime(2026, 10, 13, tzinfo=timezone.utc)
        event = Event(
            client_id=client.id,
            title="Titulo canonico",
            title_tokens="titulo canonico",
            first_seen_at=now,
            last_seen_at=now,
        )
        session.add(event)
        session.commit()
        for summary, title in rows:
            url = f"https://x.com/{title}"
            session.add(
                Mention(
                    client_id=client.id,
                    source=MentionSource.news_rss,
                    url=url,
                    url_hash=make_url_hash(url),
                    title=title,
                    summary=summary,
                    event_id=event.id,
                )
            )
        session.commit()
        return event

    def test_single_mention_title_is_summary(self, session) -> None:
        event = self._seed(session, [(None, "unica")])
        fake = FakeSummarizer()
        assert maybe_summarize_event(session, event, enricher=fake) == "Titulo canonico"
        assert event.summary == "Titulo canonico"
        assert fake.inputs is None  # no LLM call for a lone mention

    def test_multi_mention_uses_llm_over_summaries(self, session) -> None:
        event = self._seed(session, [("resumen a", "t a"), ("resumen b", "t b")])
        fake = FakeSummarizer()
        assert maybe_summarize_event(session, event, enricher=fake) == "RESUMEN"
        assert event.summary == "RESUMEN"
        assert fake.inputs == ["resumen a", "resumen b"]

    def test_failure_keeps_previous_summary(self, session) -> None:
        event = self._seed(session, [("a", "t a"), ("b", "t b")])
        event.summary = "vieja"
        session.commit()
        assert maybe_summarize_event(session, event, enricher=FakeSummarizer(None)) is None
        assert event.summary == "vieja"

    def test_no_inputs_noop(self, session) -> None:
        event = self._seed(session, [])
        assert maybe_summarize_event(session, event, enricher=FakeSummarizer()) is None


class TestLLMEventSummarizer:
    def test_plain_text_call_without_json_mode(self) -> None:
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": "  Resumen final.  "}}]},
            )

        enricher = _enricher(handler)
        assert enricher.summarize(["uno", "dos"]) == "Resumen final."
        body = calls[0]
        assert "response_format" not in body
        assert "uno" in body["messages"][1]["content"]

    def test_failure_returns_none(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        enricher = _enricher(handler, attempts=1)
        assert enricher.summarize(["a", "b"]) is None
