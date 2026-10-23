# code-consistency-fixes

**Objective**: repair the inconsistencies found in the 23-oct read-only audit (contract drift front/back, duplicate CSS, dead CSS, missing enhance wiring, repo hygiene) without behavior regressions.

**Why**: audit found real 422s on deep feed pages, settings fields with no UI (digest_focus_person_id drives the home RECTORA section), and dual CSS definitions that drift.

**Route**: direct inline per task (each is a small mechanical edit + test); no subagents needed. Single working tree shared with the user's parallel sessions -> work-unit commits straight to `main` (established repo practice), never branch-switch under him.

**Delivery**: work-unit commits, one per task, deploy affected services per Julio's standing rule. Forecast ~350 authored lines — under the 400 threshold, no chain needed.

**Authorized scope**: `frontend/src/**`, `backend/**` (only if a cap/test requires), `docker-compose.yml` (commit existing loopback binds), `.gitignore`, `referencia visual/`->`referencia_visual/` rename closure, `odd/tasks/*` docs. Nothing else.

## Tasks

- [x] T1 feed pool cap: `+page.server.ts` pool=min(offset+limit, 500) matching `api/mentions.py` `le=500`; check vitest feed tests; deploy dashboard if front-only. — DONE commit 4189c340 (branch feat/x-mode-settings — the checked-out branch, NOT main; shared tree, do not switch), test feed-page.server.test.ts RED->GREEN, svelte-check 0/0. Dashboard rebuild launched.
- [x] T2 settings surface: add `digest_focus_person_id` + `enrich_max_per_cycle` + `fetch_max_per_cycle` to `ClientSettings` type, settings form (person select + number inputs), `+page.server.ts` draft/PUT payload, server test asserting persisted payload. Deploy api+worker+dashboard. — DONE commit 146d7f87. Backend needed NO changes (ClientSettingsUpdate/validators already complete); front-only: types, load persons, save parse (caps 1..1000 like backend, focus ''->null), Operacion grid UI. Tests RED(3)->GREEN, full vitest 124/124, svelte-check 0/0, build ok. Dashboard rebuild launched; api/worker NOT touched (settings read per cycle).
- [x] T3 CSS dedup: single `.panel-head` and `.sidebar-section h2`; confirm intended bodies against `referencia_visual/` mockups first. — DONE 0c61def8. Mockups prove BOTH variants intentional: actores = divider base (kept global), configuracion = flex (scoped `.settings-flow .panel-head`); 24px h2 scoped too -> persons back to 21px per actores mockup. `.sidebar-section h2` :817 dead margin variant removed (:2123 border version is the mockup-true base). Zero-change on settings, contract-true 24->21px on persons h2.
- [x] T4 dead CSS removal: feed-preview-* family, .feed-channel, .news-title, .feed-empty, .filter-actions, .metric-unit (+ .metric-big .metric-unit, COMPACT_CLS/BTN_GHOST_CLS in ui.ts) — DONE 0c61def8, -107 net lines. Bare .feed-preview KEPT (NewsEntry variant) incl. accent rule. Comment referencing feed-preview padding updated.
- [x] T5 dedup byte-identical `.panel-note` / `.storage-note` — DONE 0c61def8 (later duplicates removed; storage-note second was a subset, margin lives in the first).
- [x] T6 `use:enhance` + pending on saved-searches create (creating flag), row toggle/delete plain enhance; KeywordsPanel same — DONE f604b1ec. Fixes silent draft wipe on settings when adding a keyword (full reload).
- [x] T7 single error-mapping helper `src/lib/server/api-error.ts` (errorStatus/errorMessage) adopted by 8 route server modules (10 sites); persons [id] 404 branch kept explicit — DONE e44cd156. Convention intact: loads 503, actions 502.
- [x] T8 repo: rename committed as pure renames (d44498a6, 100% similarity, +v2 mockup), loopback binds (990320a2), root .svelte-kit removed + gitignored, odd ledgers tracked (05483e2c).

## Acceptance / checks

- Per task: targeted vitest (front) or pytest (back) + `npm run check && npx vitest run && npm run build` for CSS/front tasks.
- Final: `pytest backend/tests -q`, `.venv/bin/python scripts/audit_coherence.py` (needs db up).

## Final verification (2026-10-23)

- `npm run check` 0 errors/0 warnings; `vitest run` 14 files / 124 passed; `vite build` ok — after T3-T5, T6, T7.
- `pytest backend/tests -q`: 441 passed, 1 failed — `test_summaries.py::test_day_window_follows_settings_timezone`, PRE-EXISTING and time-of-day flaky, NOT touched by this feature (backend diff vs 805b037c is empty): `resolve_digest_window` reads `datetime.now()` (builder.py:134), so before 12:00 local the 3h previous-evening extension includes the 'Tarde UTC' fixture -> coverage 2 != 1. Passes when run after noon. Candidate follow-up: freeze the clock in the test.
- `scripts/audit_coherence.py`: 5/5 OK (incl. TS<->pydantic contract — validates the T2 type additions).
- Deploy: dashboard rebuilt and recreated per front batch; served bundle greps confirm `settings-flow .panel-head` present, dead classes absent, `/saved-searches` 200. api/worker untouched (no backend changes; settings read per cycle).

## Commits (branch feat/x-mode-settings)

4189c340 T1 | 146d7f87 T2 | 0c61def8 T3-T5 | f604b1ec T6 | e44cd156 T7 | d44498a6+990320a2+05483e2c T8.
- Commit identity recorded per task below.

## Progress / evidence

(none yet)
