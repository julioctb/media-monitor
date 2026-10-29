# Source-bound facts and contextual advisory analysis

Fresh product analysis uses immutable factual selectors plus contextual analytical
prose, followed by a **separate fallible semantic review** of the fully composed
candidate. Structural acceptance and linked sources do not establish entailment,
source authenticity, external truth or equal advisory quality across models.
Historical narrative receivers remain tolerant; valid uncited historical prose
keeps its visible unbacked status. No human approval UI or historical rewrite is
introduced. Review lifecycle and the shared request budget are documented in
`digest-advisory-review.md`.

## Public factual boundary

```python
build_factual_basis(content, mentions=(), *, client_id=None)
factual_prompt_view(content)
factual_plan_schema(content=None)
render_factual_plan(content, plan=None)
require_contextual_plan(plan)
```

These pure helpers neither query the database nor mutate input objects. The
builder supplies already-windowed, tenant-owned Mention rows after story
filtering, attaches `factual_basis`, and retains that bank under
`generation.input_basis` after editorial ordering. Input indexes are not display
indexes; sorting and tail compilation never renumber the retained producer bank.

The original five required plan fields remain `basis_fingerprint`,
`headline_index`, `headline_frame`, `items` and `seleccion`. The optional
`headline_analysis` and per-selection `analysis` extend the strict plan. Direct
rendering still accepts a historical frame-only plan. **Fresh acceptance and
recovery require contextual analysis and a compatible passed review**; merely
rendering a legacy plan never mints that approval.

## Immutable bank and readable passages

| Field or bound | Contract |
|---|---|
| Envelope | `version: 1`, tenant, cut, catalogue fingerprint, stories, sources, fingerprint; new banks also carry internal `passage_scheme: readable-v1` |
| Tenant | Positive strict integer or null; never bool/string substitution |
| Cut | Date, timezone, window start and actual recorded window; nullable values stay explicit |
| Story | Stable index, sorted unique own `source_refs`, own representative `material_ref` or null |
| Source | Original source index, title, publication date, captured author, original, separately labelled derived summary, passage kind and passages |
| Original | At most 4,000 characters; independent of the 300-character derived-summary limit |
| Collections | At most 1,000 stories, 10,000 sources/own-source references and seven passages per source |
| Other limits | Title/passage at most 4,000 characters; captured author 1,000; cut strings 100 |
| Fingerprint | SHA-256 over exact typed envelope fields except fingerprint, sorted compact UTF-8 JSON, no NaN |

The evidence.v1 catalogue and its ten fields remain unchanged. Optional full
bodies expand only a nonempty exact frozen excerpt prefix after matching strict
Mention identity and tenant ownership. Otherwise only the frozen original
excerpt is used. The original database fields and archived derivative summaries
are never rewritten. The bank is an integrity envelope, not a signed capture;
a 300-character prefix cannot independently authenticate an unseen extension.

For new banks, passages prefer complete sentence endings around the existing
600-character target, otherwise whitespace boundaries. At most seven exact
contiguous slices cover the retained original, trimming only edge whitespace.
The last slice may exceed the target to preserve coverage. An exceptionally long
unbroken token, a source fragment or the fixed 4,000-character capture boundary
can remain incomplete; the reviewer must judge intelligibility and context.
This is not a guarantee that every excerpt is a good summary.

For an existing bank **without** `passage_scheme`, validation reproduces exact
legacy 600-character chunks and validates its original fingerprint before adding
anything. No default is inserted into a historical hash. Explicit unknown,
malformed or null schemes fail closed instead of downgrading to legacy. There
is no archive migration, renumbering or user-facing version feature.

Body-unavailable material uses one complete frozen-title passage, explicitly
labelled as title-only. No title/body produces an unavailable slot, not a derived
summary masquerading as an original. Publication date is never automatically an
act date; captured author is unverified identity, not account ownership.

## Contextual analytical structure

`headline_analysis` and each selected entry's `analysis` have this strict shape:

```json
{
  "premises": [{"index": 0, "source_ref": 0, "passage_index": 0}],
  "interpretation": "La invitación puede abrir interlocución académica.",
  "consequence": "Si hay continuidad documentada, podría ampliarse la cooperación.",
  "attention": "Observar si se publican propuestas concretas de colaboración.",
  "conditions": "La invitación no acredita un compromiso adoptado.",
  "relevance": "La vinculación ofrece un ámbito de seguimiento, sin atribuir facultades."
}
```

There are one to four unique premise selectors, all belonging to the analytical
entry's own story. The existing atomic validator checks strict selector types,
source membership, passage existence, bank identity and duplicate story indexes.
Each of the five prose strings is nonblank and at most 1,000 characters. Unknown
keys are rejected atomically. A conditional sentence can still smuggle a factual
premise; these structural checks do **not** establish semantic support.

The renderer quotes premise passages with their original source/passage indexes,
then separately labels interpretation, possible consequence and relevance.
Suggested attention and conditions use the existing `accion_sugerida` and
`condicion` pick fields. The headline includes all these parts. Story summaries
remain code-owned literal reporting; contextual headline, why-importance and pick
prose remain model-authored, never swept into `derived` merely because wrappers
are code-rendered. Source bindings establish provenance only.

Closed frame/action enums remain for compatibility, but no longer replace fresh
contextual analysis. Categories remain `decision`, `riesgo`, `ruido`, `a_favor`.
There is no keyword classifier, subject hardcoding, negative-tone floor or
volume-based selection padding. The conditional minimum of three substantive
decisions is a generation and review requirement, not a deterministic quota.
Explicit empty selection remains possible without ceremonial filler.

## Prompt and receiver compatibility

The contextual schema fixes the bank hash and legal story/source/passage choices,
keeps nested selector references resolvable, and is sent unchanged in both guided
and plain requests. `factual_plan_schema()` retains the unbound structural API.
The atomic validator remains authoritative for uniqueness and ownership.

The prompt carries captured source material, own-story navigation choices,
registered focus name/role/organization, coverage and measured indicators. Missing,
deleted or foreign focus never selects a substitute. The monitored subject is
not necessarily reader, protagonist, responsible actor or incumbent. Candidate
profiles gain no government powers. Missing focus permits general analysis.

Frozen prior material retains its own namespace, actual date/window, first-12
story bound and every selected story's own references. Derived summaries remain
identified as derivatives; coverage tone, circulation and registered profiles
are not factual premises. New selectors cite current originals only; prior input
never becomes an implicit current-source citation or a verified comparison.

The payload still uses the existing narrative keys and receiver. Empty/noise/
no-provider/failure paths retain factual cards and coverage, label analysis
unavailable, and invent no political categories. Tail selections remain protected.
Raw completions, including valid fences, are preserved before strict decoding;
unclosed fences are not repaired. The unbudgeted legacy HTTP factory retains
its original 60-second timeout and fence-stripping behavior.

## Verification boundaries and intentional expectation replacements

Synthetic HTTP and fake-judge fixtures prove wiring, scope coverage, budgets,
rejection and recovery, **not real semantic quality**. The readable pilot and
independent consumed-contract review remain separate evidence.

Superseded focused expectations are explicit: the private schema now permits
optional analytical objects; model-authored advice no longer has code-derived
origin; a two-attempt planning fallback cannot claim model success without
review; closed-fence planning success consumes a separate review request; detached
regeneration requires proposal plus passed review rather than one logical call.
Unchanged source, tenant, strict-index, receiver, agenda, export and restoration
assertions remain. Tests use explicit `reviewed_factory` injections, never
silently activate configured credentials to obtain synthetic review approval.
