# panel-v3-ui — Redesign v3 «Panel de monitoreo informativo»

Objective: implement the v3 visual design (`referencia_visual/v3/Panel-de-monitoreo-informativo`) across the media-monitor SvelteKit frontend in phases, preserving existing behavior, data semantics and copy rules.
Worktree `/Users/julioctb/Desktop/Proyectos/media-monitor-worktrees/panel-v3` · branch `feat/panel-v3-ui` @ 45dc4695 (feat/digest-brief-v3 HEAD) · `frontend/node_modules` symlinked from main checkout (lockfile diff 9fbad51a..45dc4695 empty).
Delivery: one work-unit commit per phase on the feature branch; push/PR/merge/deploy only on explicit user authorization. Engram mirror: PENDING (mem_* unavailable this session; this file is the single source of truth).
Verification: from `frontend/` → `npm run check` · `npx vitest run` · `npm run build`; plus CSS-orphan sweep after merges, computed-style spot checks vs mockup, responsive probes at mockup breakpoints. No screenshots unless Julio asks.

## Specs (verbatim from Julio's brief, 28/oct)

- **S1** «Work exclusively on the Media Monitor frontend, implementing only the visual and UX changes requested by the user.» PROJECT `/Users/julioctb/Desktop/Proyectos/media-monitor`.
- **S2** «VISUAL REFERENCE — READ ONLY `/Users/julioctb/Desktop/Proyectos/media-monitor/referencia_visual/v3/Panel-de-monitoreo-informativo`» — «The reference may contain untracked files: read it from that absolute path without modifying, moving or deleting it.»
- **S3** «Another session owns historical report regeneration, editorial validation, prompts, event associations and backend work. Do not repeat or interfere with those operations.»
- **S4** ISOLATION: «Create a NEW Git worktree under `/Users/julioctb/Desktop/Proyectos/media-monitor-worktrees/`» · «Use a unique frontend branch based on the current feat/digest-brief-v3 commit.» · «Never switch branches, reset, clean, stash or commit in the original checkout.» · «Preserve all existing user changes and untracked files.» · «Initialize this worktree’s own CodeGraph index when needed; never copy another checkout’s index.» · «Reuse existing frontend dependencies without installing or updating packages.»
- **S5** ALLOWED: «Svelte presentation components and page/layout markup. CSS, visual assets and presentation tests. Existing frontend functionality and data semantics must remain intact. User-visible copy must be neutral, professional Spanish.»
- **S6** READ-ONLY, do not modify: «backend/** · scripts/**, migrations, Docker, environment or deployment configuration · odd/tasks/** or the other session’s tracking documents · referencia_visual/** · API clients, shared data contracts, evidence/provenance validators, indicator calculations, or server-side loaders/actions · Package manifests or lockfiles. If a requested visual change genuinely requires crossing one of these boundaries, stop that portion and report the exact file, required change and reason. Do not silently expand scope.» *(This feature doc is a NEW file `odd/tasks/panel-v3-ui.md`; no existing doc touched.)*
- **S7** DATA SAFETY: «Do not generate, regenerate, approve, restore or replace reports. Do not change news, event links, classifications, people, agenda or settings. Do not call mutating API endpoints or run shared-database migrations. Do not change the meaning of source references, “No respaldado”, indicators or current/prior evidence. Missing data must not be replaced with invented information. Preserve existing behavior; the mockup does not authorize new business capabilities.»
- **S8** WORKFLOW: load media-monitor + svelte skills · inspect screen/components/reference before editing · reuse existing components, no parallel implementations · ask one focused question when unspecified · all edits inside the worktree.
- **S9** VERIFICATION: the three npm gates from the worktree frontend; isolated fixtures for mutation-related tests; preview bound 127.0.0.1 on an unused port, URL in the report; «No screenshots unless requested.»
- **S10** DELIVERY: report worktree, branch, changed files, observed checks, preview URL; «Do not push, create a PR, merge, deploy or integrate into the original checkout without explicit authorization.»

## Tasks

Route: inline unless noted. Phase order confirmed by the T0 map; one work-unit commit per phase.

- [x] T0 [S2 S8] Design/runtime map — delegated read-only explorer; mapa recibido íntegro (Log L4).
- [x] T1 [S5] Tokens & base: remap de valores `@theme` a la paleta v3 (pasos derivados marcados), Georgia/Helvetica, 16/1.6, radius-panel 12, focus ring v3. Commit ef4158f9.
- [x] T2 [S5] Shell: sidebar rail 232/88 + collapse, drawer móvil ≤768 (focus trap + inert), mobile-header, versión; estado presentacional (Svelte 5 runes). Commit fbb08d25.
- [x] T3 [S5] Shared pieces: kit v3 (h1-h4 serif, `.button/.primary/.subtle`, `.icon-button`, `.text-link`, `.source-badge`), page-title v3. Commit 9ffd2a6c. `chip`/`eyebrow` quedan por página (roles distintos).
- [x] T4 [S5] Feed view — restyle v3: intro/estado, toolbar (pestañas fuente, tono c/conteos, búsqueda), items feed-item, columna contexto (periodo, origen, medios, histórico, seguimiento); tarjeta vía NewsEntry/MentionCard.
- [x] T5 [S5] Eventos view — restyle v3: intro `events-intro` + segmented de alcance, grid `events-list`, tarjeta `event-card` v3 (mini-id `EVENTO #id`, headline link, summary, footer de conteos); detalle /events/[id] con badges fuente/tono del kit en menciones. Slots mockup sin datos en la app omitidos (prioridad, tipos de fuente, seguir, búsqueda).
- [ ] T6 [S5] Agenda view.
- [ ] T7 [S5] Personas view.
- [ ] T8 [S5] Detalle (dialog) + query launcher: presentation over EXISTING data/routes only; report any capability gap instead of inventing it.
- [ ] T9 [S5] Remaining pages under the new shell (home digest, campo, consultas, stats, settings, revisiones, saved-searches, events/[id], persons/[id]): compatibility pass only.
- [ ] T10 [S5] Login route — OPEN DECISION: the app has no auth by design (dev phase); visual-only route vs skip → ask Julio when reached.
- [ ] T11 [S5] Close-out: orphan sweep, accidental-duplicate selector sweep, per-screen structural verification vs mockup DOM, responsive/overflow probes, full gates, delivery report [S9 S10].

## Log

- L1 (2026-10-28): brief recibido verbatim (S1–S10). Setup hecho: worktree `panel-v3` + rama `feat/panel-v3-ui` @ 45dc4695, `node_modules` symlink (lockfiles idénticos), worktree previo `digest-ui` intacto y atrás sin commits propios. CodeGraph init lanzado en background sobre el worktree.
- L2 (2026-10-28): Julio eligió **«Redesign v3 completo, por fases»** (clarify). T0 mapper delegado (read-only) antes de tocar código.
- L3 (2026-10-28): CodeGraph del worktree inicializado. Preview dev (baseline pre-redesign, árbol de desarrollo del worktree): `http://127.0.0.1:5177/` — SSR 200 ~206KB con datos reales vía API 127.0.0.1:8000; sin `.env` (API_BASE_URL por env del proceso).
- L4 (2026-10-28): Mapa T0 (íntegro en transcript `~/.hermes/cache/delegation/live/deleg_2ff4b992/task-0.log`). Claves: `styles.css` del mockup es INPUT tailwind (`@apply tw:*`); lo servido es `assets/css/tailwind.css` compilado → portar resolviendo utilidades. Shell = inversión topbar→sidebar 232/88px, overlay ≤768 (`body.sidebar-collapsed` NO persistido). Colisiones de nombre con app.css: `.sidebar`(:2084) `.topbar`(:91) `.chip` `.intro` `.field` `.active/.error`, 3 skins de botón → puertos con scope + auditoría por página. MQ mockup: 480/600/768/1024/1050/1100/1150/1250/1440min/769min/hover/reduced-motion/print/max-h600. Interacciones demo selladas (localStorage `mine-*`, `ask()` grep local). Decisiones diferidas A SU FASE: (a) daily-view vs home digest v2 — el mockup manda look, no features; (b) login sin backend auth; (c) semántica real del query launcher; (d) detail-dialog ruta vs dialog. Empieza T1 (tokens).
- L5 (2026-10-28): Verificación T1+T2. Gates: svelte-check 0/0, vitest 355 OK, build OK (×2). Fidelidad: computed styles del shell = 0 deltas vs mockup servido estático (1280; server python :8901 sobre el directorio de referencia, solo lectura). Móvil 390: sin overflow, drawer/header correctos. Pendiente T11: barrer la matriz responsive completa. Lección de herramienta: el wrapper `js()` del browser exige IIFE invocada y devuelve string.
- L6 (2026-10-28): T4 (aa3d7d92, writer sa-0-1ee28bfc) VERIFICADO por padre: scope exacto 9 archivos front+doc, tree limpio, vitest re-ejecutado, browser: /feed con 50 `.feed-item` (tone/source badges), toolbar y columna contexto v3, cero markup legacy; home rinde las tarjetas compartidas (MentionCard) y el rail queda intacto; sin overflow 390–1280. Omitidos del writer correctos (sin capacidad nueva: preset periodo, guardados, paneles personas/fechas, iconos badge, compact). Detalle de evento permanece en ruta /events/[id]; el dialog global es T8.
