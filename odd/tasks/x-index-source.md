# Feature: x-index-source — cobertura X vía índice de Google News

## Objective
Replicar en media-monitor la detección de X/Twitter del digest cron de Hermes (web_search `site:x.com`): ingesta de menciones X a $0 usando el índice de Google News RSS con queries `"<keyword>" site:x.com`, sin API key, como fuente aditiva junto al adapter pago existente (`twitter_x.py`, inactivo sin `X_PROVIDER_API_KEY`).

## Problem
El worker hoy loguea "X provider disabled: X_PROVIDER_API_KEY not set" — cero cobertura X. El comportamiento probado del cron de Hermes detecta tweets vía índice de búsqueda sin credenciales.

## Why (evidencia verificada 22/oct, en vivo)
- `GET https://news.google.com/rss/search?q="BUAP"+site:x.com&hl=es-419&gl=MX&ceid=MX:es-419` → 100/100 items con `<source url="https://x.com">` (tweets institucionales reales, fechas oct 5–20). El operador `site:` filtra correctamente.
- Control sin `site:` → mezcla normal (boletin.buap.mx 36, oem 7, ...).
- `app.ingest.google_news.parse_google_rss` parsea el XML tal cual → 100 RawMention con title/url/published_at.
- Redirects: hay que seguir el 302 (`ceid=MX:es` → `MX:es-419`); el adapter existente ya usa `follow_redirects=True`.
- Limitaciones aceptadas (iguales al cron): sin handle de autor (`<source>` texto = "X"); URLs son redirects news.google.com (misma convención que menciones google_news actuales); cobertura parcial del índice (outlets e institucional se indexan bien).

## Scope
- NUEVO `backend/app/ingest/x_index.py`: `XIndexAdapter(GoogleNewsAdapter)` — override solo del template de query (`"{keyword}" site:x.com`), `name="x_index"`, menciones con `source=MentionSource.x_twitter`, strip del sufijo `" - X"` del título.
- Wire en `worker.build_adapters()`: siempre activo junto a google_news (gratis, mismo endpoint, sin key).
- Tests: fixture del XML real capturado (recortado), espejo de las clases de test de google_news + test de wiring.
- Deploy: rebuild api+worker (ambos importan app.ingest). Sin cambios de front/dashbaord.

## Constraints
- No tocar cambios no commiteados de Julio (docker-compose.yml, odd/tasks/elpopular-scraper.md, referencia visual/*).
- Commits: conventional con descripción en español (estilo del repo), solo pathspecs propios.
- Branch: feat/x-index-source desde main antes del primer commit.
- Verificación: `.venv/bin/python -m pytest backend/tests -q`; ciclo worker con log `adapter x_index: fetched N`.

## Tasks
- [x] T1 — Adapter `x_index` + tests (fixture-driven, RED→GREEN): subclass con query template, source=x_twitter, strip sufijo " - X", window `when:` heredada. Commit feat. → `313f821f`
- [x] T2 — Wiring en `build_adapters()` + test wiring + rebuild api/worker + verificación de ciclo en logs (`adapter x_index: fetched N`) + coverage check en PG (`SELECT count(*) FROM mentions WHERE source='x_twitter'` tras el ciclo). Commit feat. → código+wiring commit abajo; **rebuild/verificación de ciclo/PG pendientes del orquestador** (fuera del alcance del subagent).

## Verification evidence
- 2026-10-22 (implementación, subagent):
  - RED: `ModuleNotFoundError: No module named 'app.ingest.x_index'` en la primera corrida de `backend/tests/test_x_index.py` (tests escritos primero); wiring test RED con `['google_news', 'gdelt'] != ['google_news', 'x_index', ...]` antes de tocar `worker.py`.
  - GREEN: `.venv/bin/python -m pytest backend/tests -q` → **430 passed** (suite completa, incluye 6 tests nuevos de x_index + 6 aserciones de wiring actualizadas en test_worker.py).
  - Árbol del commit 1 verificado standalone (sin wiring): 19 passed en test_x_index.py+test_worker.py.
  - Fixture `backend/tests/fixtures/x_index_buap.xml`: 3 items recortados del capture real `/tmp/gn_x.txt` (100 items, 22/oct 17:04); verificado parseable con `parse_google_rss` antes de escribir los tests.

## Progress log
- 2026-10-22: probes en vivo completados (ver Why). Doc creado por orquestador; implementación delegada.
- 2026-10-22: T1 implementado (commit `313f821f`, rama `feat/x-index-source`): `XIndexAdapter(GoogleNewsAdapter)` en `backend/app/ingest/x_index.py` — override de fetch con query `"<kw>" site:x.com` (la parent construye la query inline, no hay hook), re-etiqueta menciones a `MentionSource.x_twitter` vía `dataclasses.replace` y strippea el sufijo `" - X"`; hereda hl/gl/ceid, follow_redirects, `when:` por watermark y max_items.
- 2026-10-22: T2 implementado (commit en `worker.py`): `XIndexAdapter()` siempre activo junto a google_news en `build_adapters()`; log `adapter x_index: fetched N items, inserted M new mentions` lo emite el pipeline existente vía `adapter.name` (sin código extra). Deploy pendiente del orquestador.
- Espejo Engram (topic `odd/x-index-source/tasks`): PENDIENTE — mem_save no disponible en esta sesión; resincronizar cuando Engram vuelva.
