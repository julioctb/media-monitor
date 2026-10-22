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

## Route

Direct inline. One non-trivial file (`app/ingest/scrapers.py`: parse fn +
registry entry) + mechanical test mirroring `TestEConsultaParser` + fixture
(trimmed live capture, like `econsulta_home.html`). Under the writer trigger.

## Tasks

- [x] T1 Replace 5 dead rss_feeds via PUT /api/settings (17 -> 16) — verified readback.
- [ ] T2 Fixture `tests/fixtures/elpopular_home.html` from live capture (scripts/styles stripped).
- [ ] T3 RED: `TestElPopularParser` asserts dated links + titles, nav exclusion, registry shape.
- [ ] T4 GREEN: `parse_elpopular` + `SCRAPER_REGISTRY["elpopular"]` (home + /secciones/puebla list URLs).
- [ ] T5 Full backend tests green.
- [ ] T6 Commit (my files only; tree has Julio's parallel compose/referencia-visual changes).
- [ ] T7 `PUT /api/settings` scrapers += `elpopular`.
- [ ] T8 Rebuild api+worker (same image), deploy, verify cycle: `scraper elpopular: N links` + new feed entries.

## Acceptance

- `parse_elpopular` returns >= 10 dated article links with non-empty titles from the fixture.
- No `/reporteros/`, `/secciones/<slug>` (no date), or single-segment URLs in output.
- Worker cycle log shows `scraper elpopular: N links from https://elpopular.mx/` and
  the 5 replaced feeds fetching entries; no new feed failures.

## Evidence

(to fill per task as observed)
