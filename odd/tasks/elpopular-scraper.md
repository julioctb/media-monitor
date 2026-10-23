# El Popular scraper (elpopular.mx)

## Objective

Restore El Popular (Puebla) coverage: the outlet moved from `elpopular.puebla.mx`
(WP, had /feed) to `elpopular.mx` (custom CMS, no RSS/Atom/wp-json). Add an
`elpopular` entry to `SCRAPER_REGISTRY` following the scraper-ingest pattern.

## Context (2026-10-22)

- Feed audit: 6 of 17 rss_feeds dead. 5 replaced with live feeds via
  `PUT /api/settings` (no code): angulo7.com.mx, heraldodepuebla.com,
  contraparte.mx (category feed), urbanopuebla.com.mx,
  primeraplanapuebla.com/category/actualidad. El Popular dropped from
  rss_feeds (no feed exists) — this task recovers it as a scraper.
- elpopular.mx URL anatomy: articles carry a date `/<taxo>[/<sub>]/YYYY/MM/DD/<slug>`;
  nav noise is `/reporteros/<slug>`, `/secciones/<slug>`, single-segment pages.
  The generic `article_links()` is wrong on both ends (blocks `/secciones/...`
  articles, admits `/reporteros/...`), so the parser filters on the date shape.
- Verified live: prototype parser returned 35 dated links with titles, 0 nav leaks.
- Mid-deploy discovery: contraparte.mx 403s the worker's bare
  `media-monitor/0.1` UA (proven live: bare UA 403 / browser UA 200+10 items).
  feeds.py now reuses article_fetch's BROWSER_HEADERS (commit 69caa4c0).

## Route

Direct inline. One non-trivial file (`app/ingest/scrapers.py`: parse fn +
registry entry) + mechanical test mirroring `TestEConsultaParser` + fixture
(trimmed live capture, like `econsulta_home.html`). Under the writer trigger.

## Tasks

- [x] T1 Replace 5 dead rss_feeds via PUT /api/settings (17 -> 16) — verified readback; cycle 20:31 UTC fetched all 5 new feeds.
- [x] T2 Fixture `tests/fixtures/elpopular_home.html` from live capture (scripts/styles stripped, 190KB, 35 dated links dedup).
- [x] T3 RED: `TestElPopularParser` (ImportError on missing symbol) + imports.
- [x] T4 GREEN: `parse_elpopular` + `SCRAPER_REGISTRY["elpopular"]` (home + /secciones/puebla).
- [x] T5 Suite: 441 passed with scraper, 442 passed after UA fix.
- [x] T6 Commits: 75e8cd83 (scraper), 69caa4c0 (browser headers) — my files only; tree keeps Julio's compose/referencia-visual changes.
- [x] T7 `PUT /api/settings` scrapers -> ['diario_laredaccion', 'e_consulta', 'elpopular'].
- [x] T8 Rebuild api+worker with BOTH commits, deploy, verify cycle: `scraper elpopular: N links`, contraparte 200, no feed failures.

## Acceptance

- `parse_elpopular` returns >= 10 dated article links with non-empty titles from the fixture.
- No `/reporteros/`, undated `/secciones/<slug>`, or single-segment URLs in output.
- Worker cycle log shows `scraper elpopular: N links from https://elpopular.mx/` and
  the 5 replaced feeds fetching entries; no new feed failures (incl. contraparte 403 gone).

## Evidence

- T1: settings readback 16 feeds; worker cycle 2026-10-22 20:31 UTC hit all 5 new feed hosts.
- T4/T5: `pytest tests -q` -> 441 passed (then 442 with UA test), 0 failures.
- T6: git 75e8cd83, 69caa4c0 on main.
- T7: PUT response scrapers list includes elpopular.
- T8: containers recreated 20:36 UTC, code verified inside (elpopular=6, ua_fix=2).
  First cycle 20:37 UTC: `scraper elpopular: 35 links` (home) + `13 links` (/secciones/puebla);
  contraparte feed `200 OK, 10 entries` (was 403); 0 feed failures in cycle
  (was 12/cycle from 6 dead feeds); rss_custom 211 items, scraper 156 items.
  inserted 0 new mentions = correct: no BUAP/Lilia Cedillo story on today's front page.
