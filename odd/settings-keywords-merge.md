# settings-keywords-merge

**Objective:** per `referencia_visual/configuracion-media-monitor.html`, keywords is a PANEL inside the single Configuración page — not a `/keywords` route nor a nav sub-tab. Kill the route, the nav children, and all dead code in the same pass (Julio's standing rule).

**Mockup contract (extracted — do not re-derive):**
- Page grid: `.layout{display:grid;grid-template-columns:220px minmax(0,1fr);gap:24px;margin-top:28px}` wrapping `nav.section-nav` + `div.stack` (panels).
- `.section-nav{align-self:start;position:sticky;top:20px;padding:12px;border:1px solid var(--border-soft);border-radius:var(--radius-lg);background:var(--bg)}`; links `display:block;min-height:44px;padding:10px 12px;border-radius:var(--radius-sm);font-size:14px;font-weight:600`; hover `background:var(--surface);color:var(--fg)`. `aria-label="Secciones de configuración"`.
- Anchor order EXACT: `#palabras-clave` (first), `#operacion`, `#fuentes`, `#llm`. Panel headings/notes per mockup: keywords h2 "Palabras clave", note "Términos que activan el monitoreo, asociados a su idioma."
- `@media(max-width:900px)`: `.layout{grid-template-columns:1fr}`; `.section-nav{position:static;display:flex;flex-wrap:wrap;gap:4px}`; `.section-nav a{flex:1 1 auto;text-align:center}`.
- Topbar nav: single link **Configuración** (no children) — mockup is a single-entry nav for this page.
- Keywords panel internals already exist in `lib/components/KeywordsPanel.svelte` (form term+language+Añadir, table, empty "No hay palabras clave configuradas.", status aria-live). Reuse AS-IS; do not fork a second keyword markup.

**Current state (verified):**
- `routes/settings/+page.svelte`: panels `#operacion` :191, `#fuentes` :289, `#llm` :459; comment :20 "Keyword CRUD lives on /keywords".
- `lib/components/KeywordsPanel.svelte`: supports `action=''` (page's own actions) vs `/keywords` cross-post; `lib/keyword-actions.ts` shared actions module.
- `routes/+layout.svelte`: group (children General `/settings`, Palabras clave `/keywords`) + children rendering :99 + `isActive` children `.some()` :51.
- `routes/keywords/+page.{server.ts,svelte}`: standalone page to DELETE.

**Tasks:**
- [x] T1 tests first: settings server test gains keyword actions coverage (add/toggle/delete via page actions) — RED. *(4 new tests added; RED confirmed: `actions[name] is not a function`, 4 fail / 4 pass.)*
- [x] T2 `settings/+page.server.ts`: load also returns keywords (port from keywords route load); actions spread/delegate to `lib/keyword-actions.ts` so `KeywordsPanel action=''` hits them. GREEN. *(load: `listKeywords().catch(() => [])` beside scrapers; `create/toggle/delete` delegate; 8/8 pass.)*
- [x] T3 `settings/+page.svelte`: wrap panels in `.layout` grid + `section-nav` (4 anchors, palabras-clave first, mockup CSS verbatim incl. 900px media query); render `<KeywordsPanel>` as first panel with `action=''`. NO duplicated keyword CSS — component styles stay scoped in the component. *(Grid/section-nav CSS already existed verbatim in app.css as scoped `.settings-layout`; panel added outside the settings `<form>` to avoid nested forms; anchors palabras-clave→operacion→fuentes→llm.)*
- [x] T4 nav (`routes/+layout.svelte`): Ajustes group children → single link (label `Configuración` per mockup topbar); DELETE the children-rendering branch `{#each tabs}` and the children `.some()` in groupActive — dead code removal, not disabled code. *(Also dropped now-unused `NavNode`/`children` typing and `activeTabs`.)*
- [x] T5 DELETE `routes/keywords/` (+ its test file if exists); grep `'/keywords'` references — KeywordsPanel's cross-post default may simplify to always-page-actions if nothing else cross-posts; remove now-dead props/branches in the component in the same pass. *(No keywords-page test existed; `actionBase`/`actions` props and `action()` helper removed — component posts `?/create|?/toggle|?/delete` directly.)*
- [x] T6 verify (observed output per command): `cd frontend && npm run check && npx vitest run && npm run build`; `.venv/bin/python scripts/audit_coherence.py` (db container is up; check 1 routes↔nav must pass with /keywords gone — if the audit hardcodes a routes list containing /keywords, update the audit's expectations ONLY if it derives them from the filesystem, else report). *(check: 0 errors 0 warnings; vitest 12 files / 97 tests pass; build OK (adapter-node); audit 5/5 `[OK]` incl. check 1 routes↔nav — audit derives routes from the filesystem, no edit needed.)*

**Constraints:** backend untouched. No new deps. Preserve pre-existing dirty `docker-compose.yml` (never commit it). If the audit check-1 literal-href rule needs `href: '/settings'` shape changes, keep ONE literal entry for settings.

**Route:** delegated writer; risk medium (UI structure + route removal) → writer self-verifies full frontend triad + coherence audit; parent spot-checks one command. Deploy after: dashboard image only.
