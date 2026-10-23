# home-digest-v2 — Reestructura de la página principal (Resumen diario)

**Contrato visual**: `referencia_visual/resumen-diario-media-monitor_v2.html` (en el checkout principal
`~/Desktop/Proyectos/media-monitor`; esta copia worktree no lo incluye — tomar reglas de ahí).
**Base**: `main` @ `4db43611`, worktree `~/Desktop/Proyectos/media-monitor-worktrees/home-digest-v2`, rama `feat/home-digest-v2`.
**Autorización**: Julio entrega el mockup v2 (22/oct) tras definir la reestructura; alcance completo front + builder.

## Objetivo

La home deja de ser «digest con cards» y pasa a **reporte editorial**: resumen negativo arriba,
resumen general de 3 fuentes (medios / redes / campo), detalle narrativo por bloques, y sidebar
de seguimiento. Copy y orden EXACTOS del mockup v2 («Sintesis del día», «Interpretación
actualizada», etc. — respetar literal, incl. «Sintesis» sin tilde).

## Cambios de contrato (contenido v2)

| Sección v2 | Fuente de datos | Tipo |
|---|---|---|
| Header | existente; eyebrow + nombre de rectora (focus person, fallback «BUAP»); chip Plantilla/IA **eliminado del home**; meta «Interpretación actualizada…» + nextCut (existe) | front |
| «Sintesis del día» | `summary.narrative` | front (copy) |
| Noticias negativas | derivada **front** de `eventSentiment` (ya cargado): eventos mayororía negativa, máx 3, `fuente · fecha` + título con link a `/feed?since=DAY&until=DAY`; ocultar si 0. Muere «Puntos de atención» como sección (el `why_it_matters` queda en data) | front |
| Resumen general | 3 cajas: Noticias / Redes / **Datos de Campo con tono propio** → `tones` extiende a `{media, social, field}`. Vacíos: «Sin calcular» (media) / «Sin datos». `section-note` = N fuentes activas real. «Temas en tendencia» muere | query |
| Resumen detallado / Noticias | agrupadas por tema (h4 = label de topic), narrativa del item + `Fuente: … Confianza: …`; **sin cards ni links** (NewsEntry queda solo para /feed) | front |
| Resumen detallado / Agenda | **NUEVO** `content.agenda: [{when, status?, title, source?}]` (prompt v2; ocultar si vacía) | builder |
| Resumen detallado / Rectora | **NUEVO** `content.rectora.activity: [{when?, status?, text, channel?}]`; el tone/watch resumen desaparece del home | builder |
| Resumen detallado / Redes | por fuente configurada (label de settings; groups incl.): `redes[src].note` **NUEVO** (narrativa LLM cuando hay datos); fuente configurada sin datos → línea fija «Sin novedades fechables en la ventana.»; **TikTok: no existe source type en backend → el bloque solo aparece si hay datos** | builder + front |
| Limitaciones de cobertura | = `content.pendientes` re-etiquetado; `coverage.gaps` sale del home | front |
| Sidebar Historial | + «ver mes anterior →» (param `before=YYYY-MM-01` en query de days; page.server + test) | query |
| Categorías identificadas | % `byTopic/total`, top 5, barra `width:%` | front |
| Personas mencionadas | rename de Actores; role·org + N menciones + link detalle; la nota «En el resumen diario» del mockup es placeholder → omitir | front (copy) |
| Cobertura del día (sidebar) | total; «Categorías N de 9» (`activeTopics`); «Eventos creados» = count real (`liveEvents`, el «—» del mockup era su falta de dato); **«Por término de búsqueda» = menciones por keyword del día — endpoint/payload nuevo** | query |
| Nav | el mockup agrega «Agenda» al nav — **defer** (no existe la ruta; el audit routes↔nav fallaría) | — |

Muere también del main: link «Ver el feed ↓», details «Texto plano (RAG)», day-jump móvil, sección
Datos de campo standalone, desglose «Cobertura del día» de main, chip de modo.

## Reglas permanentes (Julio)

- Sección sin datos → **ocultar**, nunca placeholder vacío.
- Elemento removido → matar TODO su código muerto en el mismo paso (handlers, params, CSS, imports).
- Un solo CSS rule por elemento compartido; page-solo overrides de tokens. Extraer del mockup TODAS
  las reglas que toquen cada elemento (incl. `@media` y selectores compartidos).
- Fidelidad: computed styles contra valores literales del mockup, no presencia de clase.
- Tokens: mapear `--fg/--bg/…` del mockup a los de `app.css`; no duplicar paleta.

## Tareas

- [ ] **T1 (builder, backend)**: keys v2 `content.agenda`, `rectora.activity`, `redes[].note` — prompt + validador tolerante + herencia en regen (`test_llm_mode_fields_applied_and_fallback`); tests espejo. RED→GREEN. *Route: delegated (writer-A).*
- [ ] **T2 (queries/API, backend)**: `tones {media,social,field}`; menciones por keyword del día (bounds locales `zonedDayBounds`); exposición al front sin romper contractos; tests. *Route: delegated (writer-A).*
- [x] **T3 (front, columna principal)**: header/narrative copy, negative-summary, resumen general 3 cajas, daily-detail (noticias por tema, agenda, rectora, redes, limitaciones); kill-list completa del main. *Route: delegated (writer-B, tras T1–T2).*
  Hecho: 68e32a7e — header con eyebrow focal (fallback BUAP) + «Interpretación actualizada», narrative «Sintesis del día», NegativeNews (mayoría negativa, máx 3, link `/feed?since&until`), resumen general 3 cajas con `tones.field`, detalle (noticias por tema + Fuente/Confianza, agenda, rectora.activity, redes note + línea fija, limitaciones=pendientes); kill-list completa (ver el feed ↓, texto plano, day-jump, chip modo, datos de campo standalone, desglose cobertura, puntos de atención, temas en tendencia, cards NewsEntry en la home).
- [x] **T4 (front, sidebar)**: 228px, categorías %, personas, cobertura del día + keywords, «ver mes anterior». *Route: delegated (writer-B).*
  Hecho: 68e32a7e — aside 228px (220 ≤1180); Historial + «ver mes anterior» (`?before=YYYY-MM-01`, `olderBefore` en page.server + tests); Categorías identificadas (% s/total real, top 5, barra); Personas mencionadas con link a detalle; Cobertura del día (total live, categorías N de 9, eventos = liveEvents, «Por término de búsqueda» cruzando keywords activas con `/api/stats/day`).
- [x] **T5 (front, CSS)**: port del style block v2 (tokens mapeados, `@media` extraídas, sin reglas duplicadas); responsive. *Route: delegated (writer-B, junto a T3/T4).*
  Hecho: 68e32a7e — bloque digest de `app.css` reescrito con el token map (--fg→ink, --border→line…); breakpoints 1180/1020/800/600 + prefers-reduced-motion; en 1020–1180 el sidebar NO colapsa (grid 2-col ≤1020, panel de personas a ancho completo 601–1020); CSS muerto eliminado (day-jump, mode, attention, special-topic, tracked, manual-data, metric, news-card, pending, quotes); reglas compartidas (.sentiment/.feed-filter/.feed-preview) intactas para /feed. Verificación: check 0 errores, vitest 113/113, build ok.
- [ ] **T6 (verificación integral)**: `pytest`, `npm run check && npx vitest run && npm run build`, `audit_coherence` (db del compose principal), spot-check parent; nota en skill: home digest ya no renderiza via NewsEntry (anatomy = solo /feed). *Route: parent.*

Hecho: worktree creado; entorno verificado (424 tests colectan con el venv principal).

## Verificación (por work-unit)

- Backend: `~/Desktop/Proyectos/media-monitor/.venv/bin/python -m pytest backend/tests -q` (desde la raíz del worktree)
- Frontend: `cd frontend && npm run check && npx vitest run && npm run build`
- Coherencia: `.venv/bin/python scripts/audit_coherence.py` (usa la db del compose principal)

## Delivery

Forecast ~1000 líneas authored → estrategia `ask-on-risk`: preguntar chain vs PR único al cruzar el
umbral (reporte post T1–T2). Push/PR/merge = decisión de Julio. Deploy: solo tras merge, rebuild
dashboard (+api si el builder cambia el runtime del worker) y verificación de snapshot en contenedor.

## Token map (mockup v2 → app.css) — traducir variables, NO portar el `:root`

Valores idénticos en ambos lados; la app ya vive con la convención `--color-*`:

| mockup v2 | app.css |
|---|---|
| `--fg` / `--fg-2` | `--color-ink` / `--color-ink-2` |
| `--border` / `--border-soft` | `--color-line` / `--color-line-soft` |
| `--muted` / `--meta` | `--color-muted` / `--color-meta` |
| `--accent*`, `--danger`, `--success` | `--color-accent*`, `--color-danger`, `--color-success` |
| `--surface` (sin def explícita en v2) / `--surface-warm` | `--color-surface` (#f5f5f7) / `--color-surface-warm` |
| `--bg` (blanco) | sin token: fondo existente del layout |
| `--radius-sm/lg` (8/18px), `--radius-pill` | `--radius-control`/`--radius-panel`, pill = utilidad tailwind |
| `--text-xs…2xl` | escala tailwind existente (`--text-base` 17px, `--text-lg` 21px) |
| `--font-*`, `--tracking-display` | idénticos |

Breakpoints del mockup a respetar: 600 / 700 / 800 / 1020 / 1180 px + `prefers-reduced-motion`.
Sidebar 1020–1180: verificar regla específica del mockup antes de decidir el colapso.

## Notas

- Mirror Engram `odd/home-digest-v2/tasks`: **pendiente** (sin herramientas engram en esta sesión);
  este archivo es la fuente de verdad hasta resincronizar.
- Sesión paralela activa en el checkout principal (`feat/x-mode-settings`) — no tocar ese árbol.
