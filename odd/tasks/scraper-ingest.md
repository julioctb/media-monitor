# Feature: scraper-ingest — Scrapers para medios sin RSS

## Objetivo
Ingerir noticias de sitios sin RSS (Diario La Redacción, e-consulta) vía scrapers
configurables, con el mismo pipeline que los feeds (match de keywords, dedupe,
sentiment). Extensible: agregar un medio nuevo = parser nuevo en el registry.

## Problema
El feed solo cubre `news_rss` / `rss_custom` / `gdelt`. diariolaredaccion.mx y
e-consulta.com no publican RSS (verificado 2026-10-15: /feed, wp-json, rss.xml 404,
solo sitemap.html). Sus notas sobre BUAP no aparecen.

## Diseño
- `MentionSource.scraper = "scraper"` nuevo valor del enum.
- `settings.scrapers` JSON (lista de keys del registry), igual patrón que `rss_feeds`.
- `backend/app/ingest/scrapers.py`: registry `SCRAPERS[name] -> ScrapeSpec(base_url,
  list_urls, parse(html) -> list[(url,title)])` + `ScrapersAdapter(SourceAdapter)`
  (source=scraper, keyword best-effort como feeds.py; el pipeline revalida).
- Parsers v1: `diariolaredaccion`, `econsulta` — selectores deducidos del HTML real
  (fixture en tests/fixtures/). Solo links de artículos (>=2 segmentos, slug real).
- worker `build_adapters`: agrega `ScrapersAdapter` si `effective.scrapers`.
- API: `scrapers` en ClientSettingsOut/Update + `GET .../scrapers/available`.
- Frontend: card "Scrapers" en /settings con checkboxes (keys → settings.scrapers).
- Migración alembic: add column scrapers JSON default '[]'.

## Tareas
- [ ] T1 tests: test_scrapers.py (parsers con fixtures, adapter filtra nav/unknown keys, settings roundtrip API) — RED primero
- [ ] T2 backend: enum+columna+migración+settings_runtime+queries validator
- [ ] T3 scrapers.py: registry + 2 parsers + adapter (GREEN)
- [ ] T4 worker build_adapters + API schemas/endpoint
- [ ] T5 frontend: tipos api.ts + card en settings (+page.server.ts save)
- [ ] T6 deploy: compose build api worker dashboard, up -d, ciclo verificado en logs con menciones scraper

## Route / verificación
- Route: delegated writer (writer trigger: ~10 archivos). Verification: writer self-check (medium).
- Commands: `.venv/bin/python -m pytest backend/tests/test_scrapers.py backend/tests/test_api.py -q`;
  frontend `npm run check`. Parent spot-check + deploy en vivo al cerrar.
- Delivery: single-pr (rama feat/scraper-ingest, work-unit commits; push/PR lo decide Julio).
- Forecast: ~700 líneas.

## Estado
- T1–T5 OK (writer deleg_73be23d7, 4 commits en feat/scraper-ingest; spot-check 12 passed; suite 385+388? full 388 passed; svelte-check limpio). Desviaciones: source=VARCHAR+CHECK (sin enum PG, 0017 solo widens CHECK); ripples sancionados article_fetch.CONTENT_FETCHERS y test_api by_source.
- T6 en curso: build compose (proc_6ec249b7c8a6) → up -d → habilitar scrapers via API → verificar ciclo.

