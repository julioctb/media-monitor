# sentiment-pills-filter

**Objective:** tone filter as 3 pills — Positivo / Neutro / Negativo — on the news list of BOTH surfaces: Resumen (`DigestSections` noticias section) and Feed page. Front-only; no backend changes.

**Verified facts (do not re-derive):**
- Feed page ALREADY filters sentiment server-side: `routes/feed/+page.server.ts` param `sentiment` ∈ SENTIMENT_FILTERS (positive/neutral/negative/none); today it's a `<select id="f-sentiment">` labeled "Tono" (+page.svelte ~154-160). The param contract and `none` value remain valid in the URL — only the UI control changes.
- Digest news items carry NO per-news sentiment; they have `event_id`. `DigestSections` already receives `sentimentByEvent: Record<string,string>` (wired from home load `data.eventSentiment`) — majority sentiment per event. That is the per-news tone proxy; keys are string event ids.
- Existing pill pattern to mirror: `feed-filter` buttons + `aria-pressed` + `feedFilter` state (DigestSections ~322-334, FEED_FILTERS keys all/news/social).

**Tasks:**
- [x] T1 DigestSections: second filter group "Tono" with 3 pills (Positivo/Neutro/Negativo, that order), same `feed-filter` classes/aria pattern; single-select, clicking the active pill clears it (all shown). Filter: `sentimentByEvent[String(n.event_id)] === pill`; items WITHOUT a resolvable value only appear when no tone pill is active. Combines (AND) with the source filter. Empty result → reuse the section's existing empty/breakdown note pattern, never an empty list render.
- [x] T2 feed page: replace the `Tono` select with the same 3 pills; clicking navigates preserving all other query params (server filter unchanged); no pill active = param absent (todos). The `none` value stays server-side for old URLs but has no pill. Remove the select's dead markup/handlers in the same pass.
- [x] T3 tests: DigestSections.test.ts — filter cases (match, toggle-off, AND con source, items sin dato); feed page test if a pattern exists for its controls.
- [x] T4 verify (observed): `cd frontend && npm run check && npx vitest run && npm run build`. NO deploy (parent handles dashboard rebuild).

**Constraints:** no backend edits; `none`/server param untouched; mockup has no pills spec — visual language MUST reuse the existing `feed-filter` token styles, no new palette. Preserve dirty `docker-compose.yml` and the staged `referencia visual` rename.

- [x] T5 (follow-up 21/oct, color semántico): las pills de tono llevan su color identidad — positivo verde, negativo rojo, neutro gris — SIEMPRE desde tokens, cero hex en componentes. Fuente de verdad: las reglas `.sentiment.*` de `app.css` (~:942, fórmulas color-mix sobre `--color-success/--color-danger/--color-surface`). Extraer la fórmula a tokens (`--tone-positive-bg`, `--tone-negative-bg`, etc.) en app.css, refactorizar `.sentiment.*` a consumirlos (una sola definición de la fórmula), y los pills las consumen: estado reposo = tinte, estado activo (`aria-pressed=true`) = versión sólida coherente del mismo tono. Ambas superficies (DigestSections + feed) con las MISMAS clases globales; prohibido duplicar la mezcla o hardcodear.

**Route:** delegated writer; risk low-medium (UI filter, 2 surfaces) → writer self-verifies front triad; parent spot-checks, merges, rebuilds dashboard only.
