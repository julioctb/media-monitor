# Feature: dedupe cross-source y chip de evento en feed

## Objetivo
Que la misma noticia llegada por 2 caminos (RSS propio + Google News) no
aparezca duplicada en el feed, y que el feed muestre el evento canónico.

## Problema
- Dedupe = sha256(url normalizada); Google News reescribe URL y título =>
  hash distinto => fila duplicada (555 rss_custom vs 557 news_rss, misma nota).
- MentionOut no expone event_id/event_title => MentionCard nunca recibe
  event => sin chip aunque el clustering ya agrupa (evento 673 tiene 549/555/557).

## Tareas
- [x] T1 test RED: ingest de URL news.google.com resuelve publisher y dedupea contra el mismo publisher ya ingestado — HECHO en 88b0fcf (canonicalización GN→publisher en pipeline, fallback seguro); suite 391 passed
- [x] T2 backend: exponer resolve_publisher_url en article_fetch + pipeline canonicaliza antes de insert (fallback URL original) — HECHO: resolve_publisher_url en ingest/article_fetch.py:230, llamada en pipeline.py:156 antes del insert (88b0fcf)
- [x] T3 backend: MentionOut.event_id/event_title, attach batcheado en list endpoint (patrón persons), test — HECHO: MentionOut.event_id/event_title en api/schemas.py:70-71 + attach batcheado (bf672b4)
- [x] T4 frontend: tipo Mention event fields + pasar event a MentionCard en feed, test vitest — HECHO: chip de evento en MentionCard.svelte (MentionEventRef, bf672b4)
- [x] T5 deploy api+worker+dashboard, verificación: chip visible en evento 673, sin duplicados nuevos en ciclo siguiente — HECHO y verificado en vivo 25/oct por Julio (da1a88bb): 0 duplicados en 48h, 47/47 URLs publisher, 50 chips/37 links en HTML del feed

## Route / verificación
- Route: inline (fix acotado, archivos conocidos). Verification: writer self (medium) + parent spot check.
- Commands: `.venv/bin/python -m pytest backend/tests/test_pipeline.py backend/tests/test_api.py backend/tests/test_dedupe.py -q`; frontend `npm run check && npx vitest run`.
- Delivery: work-unit commits sobre feat/scraper-ingest (pendiente merge); push/PR decide Julio.

## Estado
- T1–T4 OK: commits 88b0fcf (canonicalización GN→publisher en pipeline, fallback seguro) y bf672b4 (event_id/event_title en MentionOut + attach batcheado + chip en feed). Suite 391 passed, vitest 48, svelte-check limpio.
- T5 verificado 25/oct: 0 grupos de URL duplicada en 48h; 47/47 menciones últimas 24h con URL de publisher (canonicalización activa en pipeline); worker ciclando (última ingesta 00:06 UTC). Chip ya verificado en deploy (50 chips / 37 links en HTML). FEATURE COMPLETA.
- Incidente paralelo: Postgres crash exit 2 01:03 UTC + recovery; 3er crash en 3 días. VM Docker al 1360% CPU crónico (host 6d sin reinicio). Load host 63→33.

## Cierre 16/nov (auditoría de obsolescencia)

Checkboxes alineados con el cierre ya declarado por Julio en `da1a88bb`
(24/oct): "T5 verificado 25/oct — FEATURE COMPLETA". Evidencia en código:
`resolve_publisher_url` (article_fetch.py:230) llamada en pipeline.py:156;
`MentionOut.event_id/event_title` (schemas.py:70-71); chip de evento en
MentionCard.svelte (MentionEventRef).
