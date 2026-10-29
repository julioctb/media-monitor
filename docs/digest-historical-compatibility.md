# Historical digest compatibility under constrained generation

## Separate producer and receiver contracts

New production generation accepts the closed factual plan documented in
`digest-factual-contract.md`. Historical narrative payloads still use
`apply_narrative` and `apply_brief`; their tolerant per-entry structure and
unbacked-prose policy are unchanged. A historical valid sentence without usable
references remains visible and unbacked. That does not make an unsupported new
provider response an accepted current plan.

The test-only `tests.digest_legacy_fixtures.historical_summary` constructs
synthetic historical rows through the real receiver, card, ordering, compilation,
export and persistence helpers. It captures original pre-editorial facts before
current rendering, rather than feeding compiled cards or source-only advisory
placeholders back into a historical receiver. It removes the current generation
receipt and replaces the fixture bootstrap revision with the synthetic archived
narrative. It is not a production bypass, a provider adapter, a migration of
stored reports or evidence that a fresh model call succeeded.

## Preserved historical guarantees

- Independent references for rationale, suggested action and condition remain
  independent. Missing or invalid action references do not borrow rationale refs.
- Current source zero and `prior:0` are different namespaces. Historical two-cut
  bindings retain both original catalogue identities and exact field texts.
- Tolerated uncited prose, optional-field omission, malformed-entry handling,
  compiled bullet identity and used-only source export remain exercised through
  explicit historical fixtures, not obsolete fresh-provider completions.
- Current-plan tests use explicit category/index choices with each story's own
  sources. They do not infer source identity from title similarity or translate
  arbitrary old prose into a verified factual plan.

## Revision restoration

A restore request updates the stored narrative and its existing root/brief
headline mirrors, persists the change, and renders the matching plain text.
It assigns a fresh `revision_restore` headline binding without borrowing the live
cut's references. News, cards, source catalogues, metrics and unrelated tenant
rows retain their previous values.

A row carrying `factual-plan-v1` loses current-plan acceptance on restoration:
`generation.status` becomes `revision_restored`, the active plan/context are
cleared, and the earlier attempt is preserved under `prior_generation`.
Repeated restores retain the same original generation rather than nesting
history without bound. The restored historical narrative remains visible; its
historical `mode` is not a factual or editorial approval certificate.

## Evidence boundary

Receiver tests, source-table equality, literal material and validated references
establish their respective structural/provenance properties. They do not prove
external truth, independent corroboration or semantic entailment of historical
political prose. New source-based fallback is labelled as unavailable analysis,
not successful model generation. No per-report human approval or new source-data
mutation is introduced by this compatibility layer.
