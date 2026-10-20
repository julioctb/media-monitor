"""Sentiment analyzer tests: the OpenAI-compatible engine, fully offline."""

import json
import math

import httpx
import pytest

from app.models.base import Sentiment
from app.sentiment.api_analyzer import DEFAULT_SCORE, ApiSentimentAnalyzer, parse_label
from app.sentiment.base import SentimentAnalyzer


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_payload(content: str = "positive", logprobs: dict | None = None) -> dict:
    choice: dict = {"message": {"content": content}}
    if logprobs is not None:
        choice["logprobs"] = logprobs
    return {"choices": [choice]}


def _request_body(request: httpx.Request) -> dict:
    return json.loads(request.content)


class TestParseLabel:
    def test_first_label_word_wins(self) -> None:
        assert parse_label("The answer is: negative.") is Sentiment.negative

    def test_case_insensitive(self) -> None:
        assert parse_label("Positive") is Sentiment.positive

    def test_no_label_raises(self) -> None:
        with pytest.raises(ValueError):
            parse_label("no label here")


class TestApiSentimentAnalyzer:
    def test_interface_conformance(self) -> None:
        analyzer = ApiSentimentAnalyzer(
            api_key="k", client=_client(lambda request: httpx.Response(500))
        )
        assert isinstance(analyzer, SentimentAnalyzer)
        analyzer.close()

    def test_requires_api_key(self) -> None:
        with pytest.raises(ValueError):
            ApiSentimentAnalyzer(api_key="")

    def test_analyze_parses_label_and_default_score(self) -> None:
        calls: list[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(_request_body(request))
            return httpx.Response(200, json=_ok_payload("neutral"))

        analyzer = ApiSentimentAnalyzer(api_key="k", client=_client(handler))
        result = analyzer.analyze("texto", "es")
        assert result.label is Sentiment.neutral
        assert result.score == DEFAULT_SCORE  # no logprobs in the response
        # Prompt shape: system rules + the text, temperature pinned.
        assert calls[0]["temperature"] == 0
        assert calls[0]["messages"][1]["content"] == "texto"

    def test_score_from_logprobs(self) -> None:
        logprobs = {"content": [{"token": "negative", "logprob": math.log(0.75)}]}

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_ok_payload("negative", logprobs))

        analyzer = ApiSentimentAnalyzer(api_key="k", client=_client(handler))
        result = analyzer.analyze("texto", "es")
        assert result.label is Sentiment.negative
        assert result.score == pytest.approx(0.75)

    def test_retries_then_raises(self) -> None:
        calls: list = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            raise httpx.ConnectError("provider down")

        analyzer = ApiSentimentAnalyzer(
            api_key="k", client=_client(handler), attempts=3, backoff_s=0
        )
        with pytest.raises(httpx.ConnectError):
            analyzer.analyze("texto", "es")
        assert len(calls) == 3

    def test_unparsable_body_counts_as_failure(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            # 200 with a shape the parser rejects -> retry path, then raise.
            return httpx.Response(200, json={"choices": []})

        analyzer = ApiSentimentAnalyzer(
            api_key="k", client=_client(handler), attempts=2, backoff_s=0
        )
        with pytest.raises((KeyError, IndexError)):
            analyzer.analyze("texto", "es")
