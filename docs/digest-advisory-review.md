# Separate fallible semantic review in the product pipeline

A structurally valid contextual proposal is staged, not immediately approved.
The actual builder composes narrative, brief, cards, evidence bindings, editorial
ordering, tail compilation, annotations and plain export **before** requesting a
separate semantic assessment. Only a complete favorable assessment permits fresh
`mode: llm` / `status: plan_applied`. A passed automatic review is fallible;
external truth, capture authenticity and independent corroboration remain
unevaluated. No self-rating, manual approval workflow or universal model-quality
claim is introduced.

## One shared physical request budget

```python
build_daily_summary(session, client_id=..., day=...,
                    generate=None, generator_factory=None)
generate_candidate(source_engine, client_id=..., day=...,
                   generate=None, generator_factory=None)

# Optional explicit caller-created factory:
factory(effective, *, phase, budget, system_prompt, response_schema)
# phase is "proposal" or "review"; return prompt -> exact raw response, or None.
```

The builder owns one existing `RequestBudget` for both phases. The default
production path calls the existing `summary_generator` with that same budget,
phase-specific Spanish instructions and response schema. The HTTP adapter charges
**before each physical request**, including transport failures and guided/plain
fallback. Injected logical calls are not reported as physical requests.

| Physical sequence | Result |
|---|---|
| Planning succeeds once; review succeeds once | Two requests, fresh reviewed acceptance |
| Guided planning fails; plain planning succeeds | Two planning requests, review unavailable, source-only result; no third HTTP |
| Planning succeeds; review fails/rejects/malforms | Source-only result; exact raw outputs and review outcome retained |
| Both planning attempts fail | Source-only result; no invented review approval |
| Explicit `generate(prompt)` only | Legacy callable compatibility, but no configured-credential activation for review |

The 120-second per-request timeout, maximum two total physical requests,
no-redirect policy, model/settings/destination and output policy are unchanged.
An unbudgeted factory call without `response_schema` keeps historical timeout and
normalization behavior. The caller-created seam can observe wire requests in an
isolated evaluation; it must forward the supplied budget into the real adapter.
No private prompt overlay is necessary.

## What the reviewer receives and must assess

`review_packet` contains the exact compiled candidate (excluding generation audit
metadata), exact analytical plan, complete retained factual bank, focus,
comparison/coverage metadata and context fingerprint. It includes the actual
plain export, not only raw proposal text. Original bank indexes remain distinct
from final display positions. Source bodies are bounded captures, not full remote
pages. Candidate/material instructions are untrusted data.

The deterministic scope inventories nonempty candidate string leaves, including
headline, news/cards, brief selections and export, excluding provenance metadata,
raw source inventories and comparison snapshots. Those excluded materials are
still supplied as context. Each scope path requires an explicit assessment:

```json
{
  "input_fingerprint": "<exact request binding>",
  "passed": true,
  "checks": {
    "attribution": true,
    "factual_premises": true,
    "omissions": true,
    "profile_relevance": true,
    "categories": true,
    "uncertainty": true,
    "distinct_attention": true,
    "passage_suitability": true
  },
  "assessments": [
    {"path": "headline", "passed": true, "reason": "Razón específica de la evaluación."}
  ]
}
```

The example omits other scope entries for brevity; a real response may not.
Strict parsing rejects coercions, unknown fields/checks, missing/duplicate/extra
paths, mismatched input hashes and any negative field or global check. The dynamic
schema is sent inside the plain request as well as guided output. Review covers
attribution/negation/approximation, hidden new factual premises, substantive
omissions, monitored-profile relevance, category justification, uncertainty,
distinct useful attention and intelligible passage context. A valid citation does
not answer these semantic questions. A fake positive judge tests the gate only.

Review wire schemas project only assessment reasons to no-pattern strings bounded
by `minLength: 2` and `maxLength: 500`; they do not expose the historical regex
type to guided decoding. Runtime acceptance rejects blank or trimmed
single-character reasons while preserving exact valid text and all existing
strict type, length, scope, fingerprint and eight-check constraints. The floor
is a mechanical degeneration guard, not evidence that a reason is meaningful.
An invalid reason fails closed after the second physical request with both raw
responses and the rejected plan retained; it never earns a third request.

## Receipts, rejection and recovery

`generation` preserves the exact `raw_proposal`, accepted `plan` or
`rejected_plan`, actual physical count and `review`. Review records method,
`passed | rejected | unavailable`, exact raw review, assessed scope, exact input
fingerprint, error class, `fallible: true` and `external_truth: not_evaluated`.
A request fingerprint binds exact plan, candidate, bank and supplied context;
it is an integrity binding, not a signature or truth certificate.

Review failure rebuilds the entire safe projection from the pre-proposal source
content and existing composition helpers. No rejected headline, card importance,
reason, category, action, condition or associated binding is left in delivered
prose/export. Raw rejection data remains intentionally available in audit
metadata. Safe factual output is not called successful political analysis.

Recovery re-renders a recorded contextual plan only under existing complete
publication/material/comparison/profile compatibility checks. It recomposes the
candidate and requires a recorded **passed**, compatible, fully covered review
whose raw response still validates against the exact recomposed request. It does
not copy arbitrary stored prose or mint approval for frame-only historical plans.
Changed analysis, source material, context, scope or review invalidates recovery.
The previous generation/review traces are retained even when recovery is refused.
Previously marked-passed receipts whose raw explanations are single characters
are ineligible for new recovery. Stored historical prose and receipts are not
rewritten or deleted by this validation change.
Revision restoration invalidates the generation plan using the existing API route;
restored historical prose cannot become newly reviewed analysis through recovery.

Detached regeneration forwards the explicit factory through the disposable clone,
records `proposal` and `review` logical calls separately, and accepts only a fresh
`plan_applied` result with a passed review and exactly those successful phases.
It does not relax the freshness guard to accept recovery. All source tables stay
in the source snapshot; builder commits and revision logging occur in the clone.
Agenda promotion remains disabled. Failed generation raises the existing
`CandidateGenerationError` carrying the recorded calls.

## Proof still required outside unit tests

The isolated synthetic suites establish mechanisms and immutability controls.
They do not establish semantic correctness of a real model or approve the pilot.
Independent consumed-contract verification and the same captured October 10 pilot
must run separately. A real passed reviewer remains fallible and does not certify
external factual truth; a negative/unavailable reviewer does not become approval.
