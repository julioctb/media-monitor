# Enrich resilience: tolerant score + backlog self-heal sweep

## Objective

Every mention ends up classified without manual backfills: the enrichment
verdict survives a missing `sentiment_score`, and the worker re-enriches
stale unclassified rows every cycle until the backlog drains.

## Problem / why

1. `EnrichmentResult.sentiment_score` is required; GLM-5.3-Flash-EXL3
   sometimes omits it → whole enrichment discarded (21 fails / 48h): row
   loses summary, topics and political label, sentiment saved only by the
   same-cycle fallback.
2. Rows ingested while `ai_provider` was local/none (16 rows, Oct 20
   23:17–Oct 21 05:04 UTC) stay `sentiment NULL` forever: the design says
   "backfillable" but nothing backfills automatically.

## Scope

- `backend/app/enrich/llm.py`: `sentiment_score` optional, derived from
  the label when absent (positive .75 / negative .25 / neutral .5);
  explicit values keep ge/le validation.
- `backend/scripts/backfill_enrichment.py`: `before` cutoff param on
  `candidate_ids`; new `sweep_backlog(session, enricher, *, client_id,
  now, limit, min_age_h)` = oldest summary-NULL rows → `backfill()`.
- `backend/app/worker.py`: `SWEEP_ENRICH_LIMIT=25`, `SWEEP_MIN_AGE_H=2`;
  best-effort call at the end of `ingest_job` when an enricher exists.

## Constraints

- Sweep must never fail the ingest cycle (try/except, log counters).
- Sweep cap is independent of `enrich_max_per_cycle` (fresh ingest keeps
  priority); backlog drains ~100 rows/h at the 15 min cadence.
- No settings surface yet — constants in worker.py, promote later if
  tuning is needed.

## Tasks

- [x] T1 tests RED: missing-score derivation + sweep behavior (old rows
  enriched, recent skipped, cap, failure counted) — commit `1d8f7d7b`
- [x] T2 `EnrichmentResult` optional score + derive validator — commit `e01b4dcd`
- [x] T3 `candidate_ids(before)` + `sweep_backlog` — commit `e01b4dcd`
- [x] T4 worker sweep hook in `ingest_job` — commit `e01b4dcd`
- [x] T5 backend tests green (185 passed) + deploy worker + verify sweep
  log line and NULL backlog drain

## Verification

- `.venv/bin/python -m pytest backend/tests -q` → 185 passed
- Worker logs: `enrich sweep: {...}` with enriched>=16 over the first
  cycles; `SELECT count(*) FROM mentions WHERE sentiment IS NULL AND
  ingested_at < now() - interval '2 hours'` → 0.

## Progress

2026-10-22: implemented, tested, deployed (worker image rebuild), sweep
verified draining the 16-row backlog in its first pass.

## Route

Inline (parent had full context loaded; 3 files + tests, ~120 loc).
Risk tier: medium → writer self-verification (full backend suite) + one
parent spot check (sweep log line + SQL count) — both observed.
