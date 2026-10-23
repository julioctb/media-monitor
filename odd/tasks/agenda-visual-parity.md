# Agenda — visual parity con referencia_visual/agenda-media-monitor.html

**Estado:** EN CURSO (2026-10-23). Autorizado por Julio: verificar `/agenda` contra el mockup (fuente de verdad) y corregir. Sin versiones v2 del mockup; `agenda-media-monitor.html` raíz es el contrato.

## Objetivo
La página `/agenda` se construvo funcional (CRUD completo, 36711682) antes de que existiera el mockup. Este pass alinea estructura y estilos al contrato visual, sin código duplicado ni parches: una regla por elemento, muerto eliminado en el mismo pass.

## Hallazgos del audit (live 127.0.0.1:3000/agenda + estático, 2026-10-23)
1. intro: feed `.intro` global (grid + card box) se filtra a agenda; mockup = flex row, h1 margin 0, botón primario; sin lead? (verify `class="lead"` en mockup).
2. Botones: pill 999/40px vs mockup `.btn` radius 8 (--radius-control), min-height 44; primario tinta.
3. Toolbar: panel box grid 2fr/1fr vs mockup flex wrap (search 1 1 300px, filter 0 1 230px) sin caja.
4. View toggle: `.segmented` en results-head + h2 «Actividades detectadas» (no existe en mockup) → `.view-controls` dentro del toolbar, pressed = ink.
5. Month: nav arriba + label abajo vs `.month-head` (h3 capitalize + controles misma fila); falta `.calendar-shell{padding-top:48px}` y `.month-notice`.
6. Calendar: celdas botón sueltas gap 4 radius 8 min-h 52 vs grilla unida border radius-md overflow hidden, `.day` min-h 98 con bordes compartidos, today = bg warm + subrayado, `.day-button` solo días con eventos («N eventos»).
7. Day-detail: panel box vs sección plana margin 24 0 + `ul` gap 16.
8. Pendientes: panel siempre visible con nota + empty-state vs `h3.pending-title` «Sin fecha completa (N)» + cards en la lista, oculto si no hay (regla de Julio: gate on data).
9. Cards: filas borderless 2 col dentro de panel vs `.activity` boxed grid `140px 1fr auto` gap 24 pad 24 radius 18; falta `dl.details` (Lugar/Fuente/Enlace con fallbacks); título h4 15 vs h3 19; notes 12.5 muted vs 14 ink-2; badge 11/600 vs 12/500 mb 10.
10. Actions: fila suelta vs columna estirada col 3 del grid; sin «Editar fecha» en cards con fecha (mockup: editar en TODAS); delete quiet `.btn.delete`.
11. Fecha: formatDayLabel corto + hora «27 oct. · 13:00»; undated → date_label + small «Fecha por confirmar».
12. Forms: gap 16 / margin 20 0 (app 14/18); inputs min-height 44; `.form-intro` 14 ink-2 vs `.help` 12 muted (separar).
13. Empty: `.empty` global (events/persons) pad 28/12 vs mockup 40 24/18 + h3+p → regla propia agenda.
14. Breakpoints: solo 720 vs mockup 800/480 (activity 1col pad 20, details grid, day 82px, actions row, month-head column, view-controls 100%).
15. `.agenda-about` details ausente (copy del mockup desactualizado: adaptar a detección real ya conectada).

## Tareas
- [x] T1 css: reescribir bloque agenda de `app.css` (2598-2848) al contrato; skin de botones 8px/44 compartido en selectores compuestos; borrar reglas muertas (`segmented` queda para eventos).
- [x] T2 markup: reestructurar `routes/agenda/+page.svelte` (intro, toolbar+view-controls, month-head/calendar/day-button/month-notice, day-detail plano, pending condicional con count, cards con details + editar en todas, empty, about); snippet único `activityCard` sin param showEdit muerto.
- [x] T3 tests: actualizar `agenda-page.view.test.ts` al nuevo markup.
- [x] T4 gates: `npm run check`, `npx vitest run`, `npm run build` (comandos separados, leer conteos).
- [x] T5 auditoría browser: estilos computados vs mockup en 1280/1020/800/600/480 + overflow probe.
- [x] T6: limpiar fila probe (id 10, título PROBE-agenda-audit-temp, baseline 6), commit, deploy dashboard, verificar bundle servido + SSR.

## Route
Inline direct (parent ya tenía todo el contexto cargado: mockup, página, CSS, skill); un solo writer, verificación browser propia. Rationale: re-transferir ~15k tokens de contexto a un worker supera el beneficio.

## Notas de diseño
- `<dialog>` nativo del mockup → paneles condicionales: decisión documentada previa (jsdom-testable). Mantener.
- `date-edited` marker: el modelo no trackea edición de fecha; no se inventa dato. Skip.
- Copy de `.agenda-about` adaptado (el del mockup describe la demo localStorage, no la app real).
- Global `.page` padding-top 40 vs 28 del mockup agenda: drift global entre mockups (cada página varía); se mantiene el global, no es drift de agenda.
