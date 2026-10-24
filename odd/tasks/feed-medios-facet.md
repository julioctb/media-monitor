# Feed — facet y filtro por MEDIO (outlet) + backfill de URLs sin resolver

**Estado:** EN CURSO (2026-10-23). Aprobado por Julio tras hallazgo: «Medios de noticias no está implementado» — correcto en las 3 capas. Decisión: backfill primero (438 news.google.com), facet limpio después.

## Objetivo
El feed no distingue MEDIOS (e-consulta, La Jornada de Oriente…): `mentions.source` es adaptador (news_rss lumps todo el RSS). El medio real vive en el dominio del `url`. Este feature: (1) resuelve el backlog de URLs de Google News, (2) agrega facet por medio al stats, (3) filtro `?medium=` en la API, (4) panel «Medios» en el sidebar del feed.

## Hallazgos (2026-10-23)
- `by_source` (stats) = adaptadores: news_rss 716, rss_custom 104, x_twitter 101, scraper 12, facebook_page 6.
- Dominio real: news.google.com 438 (backlog viejo; últimos 4 días 100% resueltos por article_fetch), lajornadadeoriente 21, diariocambio 21, quadratin 20, hipocritalector 20, impulsoinformativo 18, buap.mx 18, retodiario 18, parabolica 17, e-consulta 16, mtpnoticias 15, oem 13.
- El load del feed ya lee `?source=` (adaptador) — inutilizable como UX de medios; se mantiene, el panel usa `medium` nuevo.

## Tareas
- [x] T1 backfill: `backend/scripts/backfill_google_news_urls.py` — EJECUTADO en contenedor api: 438/438 resueltos, 0 fallidos (6 min). news.google.com ya no existe en BD.
- [x] T2 backend facet: `by_medium` en stats overview vía `medium_breakdown` (host `_outlet_of`); test `test_stats_overview` ampliado.
- [x] T3 backend filtro: param `medium` en GET /api/mentions (LIKE www-insensible con frontera '/'); test `test_mentions_filter_by_medium`.
- [x] T4 front load: parse `medium`, consulta directa (gana a pools de canal), `mediumCounts` + echo en filters; test del load.
- [x] T5 front panel: sidebar «Medios» (top 10 + `<details>` fold, links con role=button/aria-pressed, param preservado en los 3 forms).
- [x] T6 gates: pytest backend 469 ✓, svelte-check 0/0 ✓, vitest 143 ✓.
- [ ] T7 deploy api+worker+dashboard (build secuencial en curso) + verificación servida + browser audit.

## Route
Inline direct (mismo criterio que agenda-visual-parity: contexto ya cargado, un writer).

## Notas de diseño
- Normalización de dominio: lowercase + strip `www.` — UNA función compartida backend (facet y filtro usan la misma SQL/regex, sin duplicar).
- El panel lista medios por count desc, top 12 + el resto bajo <details> (contrato visual: chips del mockup feed sidebar).
- `news.google.com` residual (si Google ya no resuelve alguna): agrupar como «Google News» al final del panel; no bloquear.
