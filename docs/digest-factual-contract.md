# Constrained factual generation (T10.1 / S22)

## Scope and proof boundary

`app.summaries.factual_contract` is a pure production module: no database
queries, provider calls, source writes, builder imports or digest imports.
It supplies a source-identity/literal-reporting contract, **not** external truth
verification, universal semantic entailment, independent corroboration or a
claim of equal advisory quality across models. Literal captured publications
can themselves be wrong. A model's valid strategic choice can be unhelpful.

This is a new generation protocol, not a tightening of historical narrative
receivers. Existing uncited prose remains accepted by the historical receiver
with its honest unbacked state. Missing references alone are not a rejection
rule. No category is inferred from tone, coverage volume, citation availability
or a minimum quota. There is no human report-approval workflow here.

## Public API and integration responsibility

```python
build_factual_basis(content: dict, mentions=(), *, client_id=None) -> dict
factual_prompt_view(content: dict) -> dict
factual_plan_schema(content: dict | None = None) -> dict
render_factual_plan(content: dict, plan: dict | None = None) -> dict
FACTUAL_SYSTEM_PROMPT: str
FactualPlanError(ValueError)
```

After story filtering, before generation, the caller attaches the returned
basis as `content['factual_basis']`. Supply the effective tenant's `client_id`
and already-windowed Mention objects. The module does not mutate content,
the catalogue, Mention objects, plans or returned objects from previous calls.

The caller sends `FACTUAL_SYSTEM_PROMPT`, `factual_prompt_view(content)` and the
private schema to its provider adapter. A non-null invalid plan raises
`FactualPlanError` before any output is returned; no valid sibling is partially
applied. The adapter/caller preserves the rejected raw response and records the
actual failure. It can then call `render_factual_plan(content, None)` against
valid material for an explicitly source-only result. This must not be recorded
as accepted model analysis. A malformed/stale basis also raises: never silently
rebuild an invalid stored bank from mutable story text.

The returned payload contains **only** existing narrative keys:
`headline`, `items`, `seleccion`, `agenda`, `redes`, `personas`, `references`.
Each item has `index`, `summary`, `why_it_matters`; each selection has `index`,
`categoria`, `razon`, `accion_sugerida`. Agenda/personas are empty lists; redes
is an empty object. No new dates, agenda entries, people facts or social-account
claims are generated. Empty sections do not instruct the tolerant legacy merge
to clear previously stored prose: the integrating fresh-generation path owns
that lifecycle and must not retain rejected inherited prose in other sections.

The payload is compatible with `apply_narrative`, but that receiver was written
for authored narrative. The integrating caller must mark these **code-owned**
rendered bindings `derived` (or exact literal copies `source_material`), never
mislabel them as model-authored prose. References use existing exact paths such
as `items.0.summary` and `seleccion.3.razon`, where selection `3` is the news
index, not the selection array position. References describe recorded source
material, not entailment of every word or a verified political conclusion.
Headline storage, generation receipts, raw completions, recovery, export and
production builder routing are caller responsibilities, not hidden side effects
of this module.

## Basis envelope and provenance

The serializable basis has exact keys:

- `version: 1`, `client_id: positive integer | null`;
- `cut: {date, timezone, window_start, window}`, with nullable strings and nullable
  `window: {from: string, to: string}`; absent values become explicit null;
- `catalogue_fingerprint`: computed through the existing evidence helper;
- `stories: [{index, source_refs, material_ref}]`, preserving the current news
  order and each story's validated, sorted, unique own-source scope;
- `sources: [{source_ref, title, publication_date, captured_author, original,
  derived_summary, passage_kind, passages}]`, in frozen source-index order;
- `fingerprint`: SHA-256 of all preceding typed fields in sorted-key,
  compact UTF-8 JSON (`ensure_ascii=False`, `allow_nan=False`).

Every consumer validates the complete envelope, recomputes its fingerprint,
checks current catalogue identity and claimed catalogue fingerprint if present,
checks cut/client/story scopes, and re-derives literal passages. A changed cut,
source, story order, scope, representative or tenant invalidates the bank. Bool,
float and string indexes never substitute for integers. Unknown envelope fields
are rejected. Returned projections are detached copies.

The hash detects stale material; it is not a signature authenticating an
untrusted producer. The builder that supplies full original bodies is trusted.
A body extension beyond the legacy frozen prefix cannot later be independently
reconstructed from that 300-character prefix. The trusted initial capture,
fingerprint validation and retained envelope are distinct from truth checking.
Do not treat an attacker-recomputed hash as authenticated source capture.

The existing evidence.v1 contract remains unchanged: ten source fields, a
300-character derivative summary and a separate 300-character original excerpt.
The new bank stores up to **4,000 original characters separately** from that
300-character derivative. Optional longer content is matched by exact integer
Mention ID and, when tenant identity is supplied explicitly or in content, exact
integer tenant ownership. Its stripped prefix must match the nonempty frozen
original excerpt before expansion. Wrong/missing identity, foreign ownership,
missing full content or a changed prefix falls back only to the frozen excerpt.
No derivative summary is used as original text.

`publication_date` copies the frozen publication timestamp with its own role;
it does not establish an occurrence date. There is no normalized occurrence-date
producer in this unit, so no `occurrence_date` slot is introduced. The renderer
labels publication time explicitly, never taking an act date from `when_label`,
the cut date or source metadata. An author is a **captured**, unverified identity;
null authors stay unknown. Neither URL hosts nor derived outlet labels establish
institutional ownership. Registered people/roles and mutable story summaries
are not factual inputs to the packet.

Body passages are nonempty, contiguous original slices of at most 600 characters,
with whitespace trimmed only at their edges. At most seven cover the retained
4,000-character body. Without a body, a nonempty frozen title is a single
`passage_kind: 'title'` passage, explicitly not body text; a 953-character title
is retained as one title passage. With neither, the passage list is empty and
kind is `unavailable`. No summary or synthetic concatenation fills that gap.

Bounds are explicit and reject overflow rather than silently dropping stories:
1,000 stories; 10,000 source records/own-source references; source indexes
0–9,999; titles/originals/passages at most 4,000 characters; captured authors
at most 1,000; date/timezone/window strings at most 100; derived summaries at
most 300. The model projection omits database IDs, URLs, client ID, original
body duplication, derivative summaries and derived outlet authority. It contains
`basis_fingerprint`, `stories`, and original `sources` with `source_ref`, `title`,
`publication_date`, `captured_author`, `passage_kind`, `passages`.

## Private model plan

All five root fields are required; every object forbids extra properties:

```json
{
  "basis_fingerprint": "<64 lowercase hexadecimal characters>",
  "headline_index": 0,
  "headline_frame": "visibility",
  "items": [{"index": 0, "source_ref": 0, "passage_index": 0}],
  "seleccion": [{
    "index": 0,
    "categoria": "decision",
    "frame": "governance_followup",
    "action": "verify_record"
  }]
}
```

`headline_index` may be null. `headline_frame` remains a required known enum
even then, but is not rendered when no headline story is chosen. Item/selection
arrays may be empty or sparse; each is bounded to 1,000 and forbids duplicate
news indexes within that array. News indexes are integers 0–999 additionally
bounded by the actual bank; source references must belong to the named story;
passage indexes are integers 0–6 additionally bounded by the chosen source.
Selections preserve the model's order/category without deterministic top-ups.
Categories are exactly `decision | riesgo | ruido | a_favor`.

No model-authored headline, summary, date, author, role, rationale, action prose,
claim or provenance map is accepted. Even a verbatim source span cannot license
a generated relationship: the model chooses only already-existing passages and
closed strategic frames/actions. It cannot turn attendance into rank, an
invitation into a promise, publication time into occurrence time or a mentioned
institution into account ownership by adding text alongside a valid reference.

The seven generic frames are `visibility`, `governance_followup`,
`execution_logistics`, `reputational_exposure`, `coverage_gaps`, `negotiation`,
`institutional_positioning`. They respectively examine possible positioning,
governance follow-up, execution conditions, conditional reputation exposure,
coverage limits, possible interlocution and institutional positioning without
asserting new agreements, powers, obligations, damage or public support.

The seven actions are `verify_record`, `compare_sources`, `monitor_followup`,
`assess_scope`, `review_execution`, `prepare_response`, `defer_judgment`.
Their exact code-owned Spanish wording is included in the system prompt.
Interpretations are labelled **Lectura política**; actions are labelled
**Atención sugerida**. They are uncertain scenarios and recommendations,
parameterized only with the canonical source title, never arbitrary model text.

## Contextual selector options (T10.4.1)

The production caller uses `factual_plan_schema(content)`, not the unbound
structural schema. It builds one detached schema from the validated bank and
uses the same value for guided output and the contract inside the plain request.
The five required output keys, closed frames/actions, renderer and receiver
contracts remain unchanged. Calling `factual_plan_schema()` without content
retains the original structural API for existing consumers.

The contextual schema fixes the exact basis fingerprint; restricts headline and
selection indexes to the existing original stories; and enumerates each valid
story/source pair with only that source's available passage positions. Both
arrays are bounded by the number of input stories; an empty bank allows only
empty arrays and a null headline. With no quotable source, item capacity is zero.

Each projected story also has its captured representative `title` and grouped
`source_choices: [{source_ref, passage_indices}]`. The full publication bodies
remain in the one existing `sources` catalogue. These detached navigation fields
do not change the sealed bank, its fingerprint, original IDs, source scope or
factual authority. Prior material, focus/role safeguards and coverage metadata
remain separate. The instructions explicitly require one passage per story and
stable original indexes even when prioritizing or changing output order.

An array-length bound or `uniqueItems` cannot establish uniqueness of the
`index` property. The authoritative validator still rejects duplicate indexes,
foreign-source choices and unavailable passages atomically, including duplicate
entries whose total length fits the contextual bound. A provider may ignore or
reject schema guidance; the plain fallback receives the identical contract and
must still pass the same validator. This change adds no semantic retry, raises
no request limit and never accepts or renumbers a partial invalid proposal.
The existing shared budget remains at most two physical requests per execution.
A successful transport or synthetic probe is not real-model advisory acceptance.

## Current producer compatibility (T10.3.2)

The integrated builder augments the pure factual projection, without changing
the five-key output schema. `cut` carries the actual current date, timezone and
window. `story_metadata` is explicitly keyed by original input `index` and
contains only topic, coverage tone, publication label, repeat circulation and
the measured media-diversity/unevaluated-veracity indicators. `coverage`,
`redes` counts and `registered_people` are separate prioritization context,
not newly verified factual premises. Mutable person facts are not supplied.

`comparison_prompt_view(content['comparison'])` supplies bounded frozen prior
material in the `prior:` namespace, with actual prior date, timezone,
`window_start` and stored `window`. Its derivative summaries are named
`derived_summary`, never promoted to original passages. `prior_coverage` is
separate title/tone context, not previous authored conclusions. The existing
12-prior-story bound and every selected story's own source scope remain intact;
database identifiers and source URL fields are not projected. Current original
material still has its separate 4,000-character bank limit. This metadata does
not add two-cut claims or prior-output references to the closed plan: current
code-owned readings continue to cite their current story's own source scope.

Focus is resolved only after usable material and a callable provider are
available. With no provider, recovery may resolve focus only after finding a
structurally valid, current-basis plan. Recovery requires the same complete
publication inventory, valid frozen catalogues and comparison context, plus
the fingerprint of the supplied factual basis, focus and prioritization
metadata. A change to the prior window alone invalidates recovery. Reordering
stored display cards does not change original plan indexes. An old free-prose
report cannot acquire a new accepted-plan receipt.

Empty cuts retain their explicit no-mentions headline and pending coverage
metadata without calling the model. Source fallback retains useful code-owned
coverage counts and a dominant captured-publication title, with an explicit
analysis-unavailable label. It creates no political categories. That unavailable
reading is not substantive advice and does not prevent tail-card compilation;
accepted selections and their source identity remain protected.

The factual HTTP factory returns the exact model response, including fences,
for `decode_plan` and `generation.raw_proposal`. Only well-formed envelopes
are accepted; an unclosed fence is not repaired upstream. Factory calls without
the new response schema preserve historical fence stripping and timeout defaults.

Literal titles, bodies, stored source summaries and their provenance bindings
remain untouched. The plain-text reading copy explicitly replaces embedded
HTTP(S) links in rendered quotations or catalogue text with `[enlace omitido]`
and labels the presentation as elided with the original conserved. Provenance
resolution uses the unchanged text before this transformation. Actual catalogue
publication links remain accessible. This is presentation, not an assertion that
the elided display is byte-identical to its original quotation.

Current-producer fixtures use explicit plans from `tests.digest_plan_fixtures`.
Historical prose/optional notes/entry tolerance are exercised through the existing
receiver on detached synthetic content, never translated into accepted current
plans. Continuity rejection fixtures first assert a genuinely accepted plan;
rejected raw output is retained separately from delivered prose and bindings.
The prompt retains the conditional minimum of three decisions when at least
three substantive candidates exist, without turning it into deterministic
padding or a ceremony quota. Monitored subjects are not assumed to be readers,
affected parties or responsible authorities; candidates gain no incumbent powers.

## Deterministic rendering and limitations

Every news slot is rendered, including slots omitted by a sparse plan.
The default uses its stable `material_ref`; an accepted item chooses another
own-source passage and renders that publication's own title/date/author together.
There is no cross-story borrowing. Literal quotations remain attributed to the
publication, including negation, approximations and invitations. This protects
report-owned transformations; it does not endorse the source's claims.

`plan=None` emits a source-only headline explicitly stating that political
analysis is unavailable, no analytical selections and a safe source summary
for every news slot. A missing-material slot is labelled unavailable, not filled
from mutable derivatives. The module does not infer factual responsibility,
absolute office rankings, actor participation, commitments or dates. It does
not produce custom free-form political analysis: the closed catalogue trades
expressiveness for a deterministic factual boundary. Provider response decoding,
attempt budgets and honest fresh/fallback receipts are separate integration work.
