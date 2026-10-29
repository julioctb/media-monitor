# Preserve report meaning while presenting Spanish plain-text exports

`render_plain_text` translates source metadata and removes redundant labels only
in the reading copy. It does not rewrite analytical prose, recalculate coverage,
select stories, change stored evidence, or certify factual truth.

## Presentation rules

| Stored input | Export behavior |
|---|---|
| News source enums and social channel keys | Spanish labels; platform brands remain recognizable. |
| Unknown source identifier | Established title-case fallback, replacing underscores with spaces. |
| Empty source identifier | `Fuente no identificada`. |
| Source URL | Exact URL retained, not translated. |
| Action starting with `Atención sugerida:` or `Acción sugerida:` | Resolve provenance against the complete original first; remove only that leading label and show one `Acción sugerida:` wrapper. |
| Body words, quotations, conditions, archived summaries and captured excerpts | No label translation or prefix stripping. Existing explicitly disclosed factual-contract URL elision is unchanged. |
| Valid available comparison context | `Qué cambió`. Availability establishes supplied comparative material, not that every row proves a factual change. |
| Explicit unavailable, malformed, partial or unknown comparison metadata | `Novedades del corte`; preserve every otherwise renderable delta row and its provenance label. |
| Comparison metadata wholly absent | Historical `Qué cambió` and typed/string delta formatting remain unchanged. |

## Preservation boundary

Source keys, source order and repetitions, channel counts (including zero), story
scope, catalogue fingerprints and exact stored field bindings are unchanged.
Unlinked prose remains visible as `No respaldado` / `No respaldada`; display
normalization cannot upgrade an invalid or stale binding. The source appendix
still lists only publications actually cited by resolved fields.

## Verification path

Exercise the public formatter in `backend/tests/test_digest_export_presentation.py`
and `backend/tests/test_digest_plain_provenance.py`, then retain the advisory and
two-cut provenance regression suites. Synthetic tests establish presentation and
binding compatibility, not political quality or semantic entailment. Independent
shared-contract verification and the real-model pilot remain separate gates.
