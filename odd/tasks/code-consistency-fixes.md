# code-consistency-fixes

**Objective**: repair the inconsistencies found in the 23-oct read-only audit (contract drift front/back, duplicate CSS, dead CSS, missing enhance wiring, repo hygiene) without behavior regressions.

**Why**: audit found real 422s on deep feed pages, settings fields with no UI (digest_focus_person_id drives the home RECTORA section), and dual CSS definitions that drift.

**Route**: direct inline per task (each is a small mechanical edit + test); no subagents needed. Single working tree shared with the user's parallel sessions -> work-unit commits straight to `main` (established repo practice), never branch-switch under him.

**Delivery**: work-unit commits, one per task, deploy affected services per Julio's standing rule. Forecast ~350 authored lines — under the 400 threshold, no chain needed.

**Authorized scope**: `frontend/src/**`, `backend/**` (only if a cap/test requires), `docker-compose.yml` (commit existing loopback binds), `.gitignore`, `referencia visual/`->`referencia_visual/` rename closure, `odd/tasks/*` docs. Nothing else.

## Tasks

- [x] T1 feed pool cap: `+page.server.ts` pool=min(offset+limit, 500) matching `api/mentions.py` `le=500`; check vitest feed tests; deploy dashboard if front-only. — DONE commit 4189c340 (branch feat/x-mode-settings — the checked-out branch, NOT main; shared tree, do not switch), test feed-page.server.test.ts RED->GREEN, svelte-check 0/0. Dashboard rebuild launched.
- [x] T2 settings surface: add `digest_focus_person_id` + `enrich_max_per_cycle` + `fetch_max_per_cycle` to `ClientSettings` type, settings form (person select + number inputs), `+page.server.ts` draft/PUT payload, server test asserting persisted payload. Deploy api+worker+dashboard. — DONE commit 146d7f87. Backend needed NO changes (ClientSettingsUpdate/validators already complete); front-only: types, load persons, save parse (caps 1..1000 like backend, focus ''->null), Operacion grid UI. Tests RED(3)->GREEN, full vitest 124/124, svelte-check 0/0, build ok. Dashboard rebuild launched; api/worker NOT touched (settings read per cycle).
- [ ] T3 CSS dedup: single `.panel-head` and `.sidebar-section h2`; confirm intended bodies against `referencia_visual/` mockups first.
- [ ] T4 dead CSS removal: `feed-preview-*` family, `.feed-channel`, `.news-title`, `.feed-empty`, `.filter-actions`, `.metric-unit` — same pass, verify survivors in built bundle.
- [ ] T5 dedup byte-identical `.panel-note` / `.storage-note`.
- [ ] T6 `use:enhance` + `update({reset:false})` + pending flags on saved-searches forms and KeywordsPanel.
- [ ] T7 single error-mapping helper in `$lib/server`, adopted by settings + saved-searches server modules.
- [ ] T8 repo: commit rename `referencia visual`->`referencia_visual` (both sides, rename detected), loopback binds in compose, odd task docs; root `.svelte-kit/` -> gitignore.

## Acceptance / checks

- Per task: targeted vitest (front) or pytest (back) + `npm run check && npx vitest run && npm run build` for CSS/front tasks.
- Final: `pytest backend/tests -q`, `.venv/bin/python scripts/audit_coherence.py` (needs db up).
- Commit identity recorded per task below.

## Progress / evidence

(none yet)
