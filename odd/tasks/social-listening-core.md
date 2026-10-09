# Feature: social-listening-core

Clone of Meltwater Social Listening core loop, adapted to media-monitor.
Reference: meltwater.com/en/capabilities/social-listening + /product-tours/social-listening-analytics.
Delivery: single feature branch `feat/social-listening-core`, one work-unit commit per task,
conventional commits, no co-authored-by. Merge to main = user decision at close.
Route: delegated writer (trigger: 2+ non-trivial files across backend+frontend). Verification tier: medium (writer self-verifies).

## Objective

Meltwater's core loop on the existing `mentions` schema:
saved search → spike detection over the match set → AI summary of the spike → alert.
Everything is a query over `mentions`; no new ingest sources.

## Scope (authorized)

- `SavedSearch` persisted per client (name, q, sources, classifier/label, date-range defaults).
- Spike detection: time-bucketed counts per saved search vs trailing baseline (z-score), `spike_events` table.
- AI spike summary via the existing configured AI provider (`settings.ai_provider`), graceful no-provider fallback.
- Sentiment-shift alert: window vs previous window per saved search, routed through existing `alerts/engine.py` + `transport.py`.
- SvelteKit UI: saved-search CRUD, spike markers on timeline, spike summary card. English UI copy.

## Out of scope (phase 2+, do NOT build)

Share of voice / competitor benchmarking, 48h forecast, 15-month backfill, PDF/PPT export,
Slack/Teams transports, Reddit/forums/Twitch sources, BYOC.

## Constraints (non-negotiable)

- `client_id` on every new table and every query (multi-tenant, per skill).
- Migrations dialect-agnostic (sqlite dev.db + PG): `native_enum=False`, `sa.JSON()`, `CURRENT_TIMESTAMP`, guard PG-only DDL.
- Reuse `queries._mention_filters` as the single WHERE builder — extend, never fork it.
- Spike math = pure function, tested with frozen time; no hidden globals.
- AI summary: mocked-provider tests; missing provider must degrade to alert-without-summary, never raise.
- New scheduled work hooks into the existing APScheduler jobs in `worker.py` (pattern: `retention_purge_job`).

## Tasks

- [x] **T1** `SavedSearch` model + alembic migration + CRUD API (`/clients/{id}/saved-searches`), validation mirrors `_validate_*` helpers. Tests: CRUD + client scoping.
- [x] **T2** Spike detection: pure `detect_spike(buckets, baseline_window, threshold) -> SpikeEvent|None`; hourly buckets per saved search over trailing 14d baseline, z >= 2.5 default; `spike_events` migration; worker pass `spike_scan_job` on the APScheduler. Tests: math (spike/no-spike/empty/short-history) + job integration with sqlite.
- [x] **T3** AI spike summary: on new spike_event, top-N mentions of the spike window → provider prompt → summary stored on the event; dedupe (one summary per event); provider failure → event stays summary-less. Tests with mocked provider.
- [x] **T4** Sentiment-shift rule in alert engine: per saved search, positive/negative share window vs previous window; threshold configurable in alert settings; reuses transport. Tests: shift fires / no-shift silent / disabled silent.
- [ ] **T5** Frontend: `saved-searches` page (CRUD), spike markers + summary card on stats/dashboard; settings hook for shift threshold. Build passes; verify built CSS is served (rendered page → css asset → non-trivial bytes). No screenshots.
- [ ] **T6** Full verification pass + close-out summary (commands + observed results).

## Verification (writer runs, reports `<command>: <result>` per task and at close)

- `pytest` via the project venv against `backend/tests` (discover interpreter: `backend/.venv` or repo `.venv`; report the exact command used).
- `frontend`: typecheck + `npm run build` (or pnpm, as configured) + built-CSS-served check.
- Each migration: render offline upgrade AND downgrade SQL before calling it done (sqlite test suite does not exercise PG-only DDL).
- Layout overflow spot-check on the new page by DOM measurement if a browser session is available; otherwise note as skipped.

## Progress log

- 2026-10-09: branch `feat/social-listening-core` created from main; pre-existing WIP checkpointed as `ac3f7cb` (classifier/label mention filters — preserved, not part of this feature's tasks but T1 builds on its `_mention_filters` signature).
