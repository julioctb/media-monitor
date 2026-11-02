"""Pure provider contract tests; no live transport or model execution."""

from datetime import datetime
from decimal import Decimal

import pytest

from app.summaries.provider_contract import (
    PlanDecodeError,
    RequestBudget,
    RequestBudgetExhausted,
    decode_plan,
)


@pytest.mark.parametrize("fail_guided", [False, True])
def test_producer_invocations_share_physical_budget_after_failure_or_fallback(
    fail_guided,
):
    budget, calls = RequestBudget(), []

    def fake_post(mode, *, timeout):
        calls.append((mode, budget.used, timeout))
        if fail_guided and mode == "guided":
            raise ConnectionError("synthetic transport failure")
        return '{"choices": []}'

    def produce():
        for mode in ("guided", "plain"):
            budget.consume()  # Immediately before every physical attempt.
            try:
                return fake_post(mode, timeout=budget.timeout_seconds)
            except ConnectionError:
                continue
        return None

    assert produce() == '{"choices": []}'
    if not fail_guided:
        assert produce() == '{"choices": []}'
    with pytest.raises(RequestBudgetExhausted):
        produce()
    assert calls == [
        ("guided", 1, 120.0),
        ("plain" if fail_guided else "guided", 2, 120.0),
    ]
    assert (budget.used, budget.remaining) == (2, 0)


def test_decoder_accepts_one_object_without_coercing_values_or_mutating_text():
    raw = (
        ' {"index":0,"flag":true,"string":"0","float":1.5,"nested":[null,{"x":false}]} '
    )
    before = raw.encode()
    result = decode_plan(raw)
    assert result == {
        "index": 0,
        "flag": True,
        "string": "0",
        "float": 1.5,
        "nested": [None, {"x": False}],
    }
    assert type(result["index"]) is int
    assert type(result["flag"]) is bool
    assert type(result["string"]) is str
    assert type(result["float"]) is float
    assert type(result["nested"][1]["x"]) is bool
    assert raw.encode() == before
    result["nested"].append("changed")
    assert decode_plan(raw)["nested"] == [None, {"x": False}]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        True,
        False,
        1,
        0.5,
        b"{}",
        bytearray(b"{}"),
        (),
        {1},
        datetime(2026, 1, 1),
        Decimal(1),
        object(),
    ],
)
def test_decoder_accepts_text_only_without_mutating_rejected_input(payload):
    before = repr(payload)
    with pytest.raises(PlanDecodeError):
        decode_plan(payload)
    assert repr(payload) == before


@pytest.mark.parametrize(
    "raw",
    [
        "null",
        "[]",
        "true",
        "false",
        "0",
        '"object"',
        "",
        " ",
        "{",
        '{"a":}',
        '{"a":1,}',
        "{'a': 1}",
        "{}{}",
        "prefix {}",
        "{} suffix",
        '{"a":"\n"}',
    ],
)
def test_decoder_rejects_nonobject_or_malformed_json_without_changing_raw(raw):
    before = raw.encode()
    with pytest.raises(PlanDecodeError):
        decode_plan(raw)
    assert raw.encode() == before


@pytest.mark.parametrize(
    "raw",
    [
        '```json\n{"choices": []}\n```',
        '```\n{"choices": []}\n```',
        ' \n```json  \r\n{"choices": []}\r\n```\n ',
    ],
)
def test_decoder_accepts_only_complete_optional_json_fences(raw):
    before = raw.encode()
    assert decode_plan(raw) == {"choices": []}
    assert raw.encode() == before


@pytest.mark.parametrize(
    "raw",
    [
        "```json\n{}",
        "```\n{}",
        "{}\n```",
        "```python\n{}\n```",
        "```json {} ```",
        "prefix\n```json\n{}\n```",
        "```json\n{}\n```suffix",
        "```json\n{}\n```\n```json\n{}\n```",
        "```json\n[]\n```",
        "```json\n{} garbage\n```",
        "```json\n{}\n````",
        "```jsonx\n{}\n```",
    ],
)
def test_decoder_rejects_incomplete_or_garbage_fences(raw):
    with pytest.raises(PlanDecodeError):
        decode_plan(raw)


@pytest.mark.parametrize(
    "raw",
    [
        '{"a":1,"a":2}',
        '{"nested":{"a":1,"a":2}}',
        '{"nested":[{"a":1,"a":2}]}',
        '{"a":1,"\\u0061":2}',
    ],
)
def test_decoder_rejects_duplicate_keys_at_any_depth(raw):
    with pytest.raises(PlanDecodeError):
        decode_plan(raw)


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity", "1e999", "-1e999"])
@pytest.mark.parametrize("template", ['{"n":%s}', '{"nested":[{"n":%s}]}'])
def test_decoder_rejects_nonfinite_numbers_including_nested_overflow(number, template):
    with pytest.raises(PlanDecodeError):
        decode_plan(template % number)


def test_decoder_does_not_approve_or_coerce_semantically_invalid_choices():
    decoded = decode_plan('{"index":true,"fact_ids":["foreign"],"frame":"unknown"}')
    assert type(decoded["index"]) is bool
    assert decoded["fact_ids"] == ["foreign"]
    assert decoded["frame"] == "unknown"


def test_decoder_preserves_ordinary_json_controls_without_repair():
    assert decode_plan("{}") == {}
    assert decode_plan('{"text":"á ``` NaN","small":1e-300,"large":1e308}') == {
        "text": "á ``` NaN",
        "small": 1e-300,
        "large": 1e308,
    }
    for raw in ("\u00a0{}", "```json\n\u00a0{}\n```", "```json\n{}\u00a0\n```"):
        with pytest.raises(PlanDecodeError):
            decode_plan(raw)


def test_budget_consumption_is_bounded_and_exhaustion_preserves_state():
    budget = RequestBudget()
    assert (budget.used, budget.remaining) == (0, 2)
    assert budget.consume() == 1
    assert (budget.used, budget.remaining) == (1, 1)
    assert budget.consume() == 2
    for _ in range(2):
        with pytest.raises(RequestBudgetExhausted):
            budget.consume()
        assert (budget.used, budget.remaining) == (2, 0)


@pytest.mark.parametrize("limit", [True, False, "2", 2.0, None, 0, -1, 3])
def test_budget_rejects_invalid_or_above_cap_limit(limit):
    with pytest.raises(ValueError):
        RequestBudget(limit=limit)


@pytest.mark.parametrize(
    "timeout",
    [
        True,
        False,
        "120",
        None,
        0,
        -1,
        120.01,
        float("nan"),
        float("inf"),
        float("-inf"),
        10**1000,
    ],
)
def test_budget_rejects_invalid_or_above_cap_timeout(timeout):
    with pytest.raises(ValueError):
        RequestBudget(timeout_seconds=timeout)


def test_budget_exposes_bounded_read_only_configuration_and_independent_state():
    first, second = RequestBudget(), RequestBudget(limit=1, timeout_seconds=0.5)
    assert (first.limit, first.timeout_seconds) == (2, 120.0)
    assert (second.limit, second.timeout_seconds) == (1, 0.5)
    assert second.consume() == 1
    assert (first.used, first.remaining, second.used, second.remaining) == (0, 2, 1, 0)
    with pytest.raises(RequestBudgetExhausted):
        second.consume()
    for field in ("limit", "timeout_seconds", "used", "remaining"):
        with pytest.raises(AttributeError):
            setattr(first, field, 999)
    assert RequestBudget(timeout_seconds=1).timeout_seconds == 1
    assert first.consume() == 1
    assert first.consume() == 2
    fresh = RequestBudget()
    assert (fresh.used, fresh.remaining) == (0, 2)
