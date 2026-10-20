# Remove Laya — political via enrichment

Goal: drop the torch/nvidia/laya dependency stack (5.95GB images) now that
the canonical classification is the enrichment LLM. The only local-layer
artifact still consumed was `classifier='political'` (feed chip «Política»).

## Plan

- [ ] T1 `feat(enrich)`: `enrich/llm.py` emits `political`
      (`political|not_political|uncertain`, tolerant parse, absent = None);
      `pipeline.py` persists `classifier='political'` next to `topics`
      (same best-effort pattern). NO backfill: historical laya-era rows stay
      as-is; the new label only lands on ingests with enrichment (documented
      in the commit body).
- [ ] T2 `refactor!`: remove laya entirely —
      - pyproject: drop `laya==0.3.4`
      - worker: no `build_classifiers`/`shared_laya`/agreement; sentiment
        builder inlined (openai -> `ApiSentimentAnalyzer`, else None)
      - delete `app/sentiment/{laya_analyzer,factory}.py`,
        `app/classifications/` (political/topics/registry/base)
      - `TOPIC_LABELS` moves into `enrich/llm.py`; stats uses a static
        classifier list (`political`, `topic`, `topics`)
      - `ai_fallback_local` cascade removal (UI checkbox, schemas, runtime
        snapshot, worker log); DB column kept (no migration in this pass)
      - settings probe: no local engine construction
      - compose: drop `hfcache` volume + `LAYA_POLITICAL_CONFIDENCE_THRESHOLD`
      - `backend/scripts/eval_classifications.py` deleted with its registry
        import; gold `.jsonl` data kept for future enrichment evals
- [ ] T3 backfill: none (see T1 note).
- [ ] T4 front: chips/stats read `classifier` rows — unchanged; no laya refs.
- [ ] T5 tests rewritten inline with T1/T2; regression: enrichment persists
      political, pipeline laya-free, chip filters still green.

## Verification

- `.venv/bin/python -m pytest backend/tests -q`
- `cd frontend && npm run check && npx vitest run && npm run build`
- `grep -rn laya backend/app frontend/src` -> no dead hits
