"""Run-local provider request accounting and response decoding."""

import json
import math
import re

from app.enrich.llm import strip_code_fence


class PlanDecodeError(ValueError):
    """Provider output is not one strict JSON object."""


def _unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlanDecodeError("Duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise PlanDecodeError("Nonfinite JSON number")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise PlanDecodeError("Nonfinite JSON number")
    return number


def decode_plan(payload: object) -> dict:
    """Decode text only, optionally fenced; no coercion or fact validation.

    A fresh object is returned; the original provider text is never repaired.
    """
    if type(payload) is not str:
        raise PlanDecodeError("Provider output must be JSON text")
    text = payload.strip(" \t\r\n")
    if text.startswith("```"):
        fence = re.fullmatch(r"```(?:json)?[ \t]*\r?\n([\s\S]*?)\r?\n```", text)
        if fence is None:
            raise PlanDecodeError("Provider output has an invalid code fence")
        text = strip_code_fence(text)
        if text != fence[1].strip(" \t\r\n"):
            raise PlanDecodeError("Provider output has non-JSON whitespace")
    try:
        result = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
            parse_float=_finite_float,
        )
    except (ValueError, RecursionError) as exc:
        raise PlanDecodeError("Provider output must be one strict JSON object") from exc
    if type(result) is not dict:
        raise PlanDecodeError("Provider output root must be an object")
    return result


class RequestBudgetExhausted(RuntimeError):
    """The run has no physical request attempts left."""


MAX_REQUESTS = 2
MAX_TIMEOUT_SECONDS = 120.0


class RequestBudget:
    """Serial, run-local accounting; reuse one instance across all phases.

    Not a global/shared cross-request quota or a concurrent reservation API.
    """

    def __init__(self, *, limit: int = 2, timeout_seconds: float = 120.0):
        if type(limit) is not int or not 0 < limit <= MAX_REQUESTS:
            raise ValueError("limit must be an integer between 1 and 2")
        if (
            type(timeout_seconds) not in (int, float)
            or not 0 < timeout_seconds <= MAX_TIMEOUT_SECONDS
        ):
            raise ValueError("timeout_seconds must be finite and in (0, 120]")
        self._limit = limit
        self._timeout_seconds = timeout_seconds
        self._used = 0

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def timeout_seconds(self) -> float:
        return self._timeout_seconds

    @property
    def used(self) -> int:
        return self._used

    @property
    def remaining(self) -> int:
        return self._limit - self._used

    def consume(self) -> int:
        """Charge before transport, returning the one-based attempt ordinal."""
        if self.remaining == 0:
            raise RequestBudgetExhausted("Physical request budget exhausted")
        self._used += 1
        return self._used
