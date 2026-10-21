# rectora-identity-stamp

**Objective:** the digest's rectora section must always identify the focus person (mockup: h2 = name, note = role · org, per `referencia_visual/resumen-diario-media-monitor.html` #rectora) and the update stamp must match the mockup copy verbatim. Today's generic "Rectora / Persona focal del resumen" fallback happens because `content.personas` omits the focal person when she has 0 mentions in the window (verified 21/oct: person 4 absent, mention_count 0 is REAL data — builder count is correct, do NOT touch matching/counting).

**Tasks:**
- [ ] T1 (backend, RED first): builder stamps identity onto `content.rectora`: `name`, `role`, `org` taken from the SAME source the `personas` entries use (check `backend/app/summaries/` rectora builder + persons table columns; if role/org are not stored on persons, take the builder's existing enrichment path or leave the field absent — never invent). Test: builder output includes rectora.name for a fixture with a focal person; stays absent-tolerant. Run only the summaries/facts test files + full suite; known pre-existing failure: `test_summaries.py::test_day_window_follows_settings_timezone` (assert 2 == 1).
- [ ] T2 (frontend): `DigestSections.svelte` rectora heading uses `rectora.name ?? rectoraPersona?.name ?? 'Rectora'` and note `rectora.role/org ??` existing persona chain — content fields WIN (freshest), persona lookup stays as fallback for pre-stamp digests.
- [ ] T3 (frontend): update stamp exactly `Resumen actualizado el {DD/MM/YYYY} a las {HH:MM}` wrapped in `<time datetime={iso}>` (mockup literal pattern: "Resumen actualizado el 19/10/2026 a las 06:24"). Split `formatDisplayDateTime` output or add a dedicated pair formatter; do not change other call sites' rendering. Update/add component test if a pattern exists.
- [ ] T4 verify (observed): `.venv/bin/python -m pytest backend/tests -q`; `cd frontend && npm run check && npx vitest run && npm run build`. NO deploy, NO regen — parent handles.

**Constraints:** do not alter mention counting/matching (today's 0 is correct). Do not regen or touch live rows. Preserve dirty `docker-compose.yml`. The 21:00 cut today will stamp identity naturally post-deploy; parent verifies the cut instead of force-regenerating.

**Route:** delegated writer (builder + component + tests); risk medium → writer self-verifies full suites; parent spot-checks one command, merges, rebuilds api+worker+dashboard before the 21:00 cut.
