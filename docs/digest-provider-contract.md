# Digest provider boundary (T10.2 / S22)

`app.summaries.provider_contract` provides deterministic request accounting and
strict JSON decoding. It performs no transport, credential lookup, clock reads,
logging, retries, source lookup, factual validation or rendering. It reuses
`app.enrich.llm.strip_code_fence` after checking the complete fence envelope.
This unit does not change the HTTP factory or builder.

## Run-local request budget

```python
budget = RequestBudget(limit=2, timeout_seconds=120.0)
attempt = budget.consume()  # 1, then 2; call immediately before transport.
```

- `RequestBudget(*, limit: int = 2, timeout_seconds: float = 120.0)` creates an
  independent budget for **one entire generation run**. Reuse that exact instance
  across phases, producer invocations, transport failures and guided/plain
  fallbacks. Creating a fresh budget for each phase defeats the run-wide cap.
- `limit`, `timeout_seconds`, `used` and `remaining` are read-only public
  properties. Initially `used == 0` and `remaining == limit`.
- `consume() -> int` irreversibly charges one physical attempt and returns its
  one-based ordinal. Charge immediately before **each** actual HTTP request,
  including a request which later fails. A failure does not refund an attempt.
- Once exhausted, `consume()` raises `RequestBudgetExhausted(RuntimeError)`
  without changing either counter. There is no reset or implicit retry.
- `limit` accepts only a built-in integer in `[1, 2]`. `timeout_seconds` accepts
  only a built-in integer or float in `(0, 120]`. Booleans, strings, nonfinite
  numbers, nulls, nonpositive values and larger caps raise `ValueError` without
  coercion. Smaller positive caps support bounded configuration and tests.
- The timeout is a **per-request configuration cap**, not an elapsed-run timer.
  The transport must actually pass `budget.timeout_seconds` to its HTTP client.
  It must disable redirects and charge all physical fallback/retry requests.
  The budget does not itself enforce networking or a wall-clock deadline.
- This is serial accounting, not a concurrent reservation API, a module-global
  quota, a cross-request shared counter or a tenant-wide rate limiter. Do not
  share an instance across unrelated report requests.

The unit tests use a small synthetic producer to demonstrate two physical fake
calls across invocations, failure/fallback charging and exhaustion before a
third call. They do **not** certify HTTP factory/builder integration. Integration
must reuse the run-owned object and must not catch exhaustion as permission to
retry with a fresh budget. Legacy calls without a budget are outside this unit.

## Strict syntax decoder

`decode_plan(payload: object) -> dict` accepts **only built-in string input** and
returns a newly parsed independent dictionary. Already-decoded dictionaries,
bytes, arrays, booleans, numeric inputs, dates, decimals, tuples, sets and custom
objects are rejected with `PlanDecodeError(ValueError)`. Text-only input keeps
duplicate-key detection at the original provider boundary; a dictionary would
have already lost that evidence.

Accepted text is exactly one JSON object, optionally surrounded by JSON
whitespace (`space`, `tab`, `CR`, `LF`). An optional complete code fence may have
an opening line of three backticks followed by lowercase `json` or no language,
optional spaces/tabs, then LF or CRLF. The closing three-backtick line must be
preceded by LF or CRLF. Whitespace may surround the whole fence. Inline fences,
other languages, extra backticks, unclosed fences, arbitrary prefixes/suffixes
and multiple fenced payloads are rejected. The shared fence stripper is not
used as a repair mechanism for malformed envelopes or non-JSON whitespace.

The decoder rejects:

- null, array or scalar roots, malformed JSON, single-quoted Python literals,
  trailing commas, control characters and concatenated JSON documents;
- duplicate keys at every nesting depth, including equivalent escaped keys,
  using `object_pairs_hook`;
- `NaN`, `Infinity` and `-Infinity` using an explicit rejecting `parse_constant`,
  plus overflowing JSON floats such as `1e999` using a finite `parse_float`.

Parser `ValueError` and recursion failures become `PlanDecodeError`. No
`literal_eval`, substring extraction, prefix/suffix repair or retry is performed.
The original raw input is unchanged on success and failure. JSON scalar types
are preserved: `true` remains a boolean, `"0"` a string and `0` an integer.
Ordinary strings containing backticks or the word `NaN` remain valid strings.

**Decoding is not approval.** Empty objects, unknown keys, boolean/string
indexes, unknown frames and out-of-scope fact IDs can be syntactically valid.
They are deliberately not coerced, approved or fact-checked here. The separate
factual/plan contract must validate them against the actual source/story scope
before any accepted rendering. An invalid or exhausted generation must reach
the product's honest safe-result path; this module does not fabricate a model
success or ask for manual report acceptance. Synthetic compliance tests prove
this boundary, not universal model compatibility or analytical quality.
