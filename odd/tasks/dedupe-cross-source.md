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
- [ ] T1 test RED: ingest de URL news.google.com resuelve publisher y dedupea contra el mismo publisher ya ingestado
- [ ] T2 backend: exponer resolve_publisher_url en article_fetch + pipeline canonicaliza antes de insert (fallback URL original)
- [ ] T3 backend: MentionOut.event_id/event_title, attach batcheado en list endpoint (patrón persons), test
- [ ] T4 frontend: tipo Mention event fields + pasar event a MentionCard en feed, test vitest
- [ ] T5 deploy api+worker+dashboard, verificación: chip visible en evento 673, sin duplicados nuevos en ciclo siguiente

## Route / verificación
- Route: inline (fix acotado, archivos conocidos). Verification: writer self (medium) + parent spot check.
- Commands: `.venv/bin/python -m pytest backend/tests/test_pipeline.py backend/tests/test_api.py backend/tests/test_dedupe.py -q`; frontend `npm run check && npx vitest run`.
- Delivery: work-unit commits sobre feat/scraper-ingest (pendiente merge); push/PR decide Julio.

## Estado
- T1–T4 OK: commits 88b0fcf (canonicalización GN→publisher en pipeline, fallback seguro) y bf672b4 (event_id/event_title en MentionOut + attach batcheado + chip en feed). Suite 391 passed, vitest 48, svelte-check limpio.
- T5 parcial: deploy 01:04 UTC; API sirve event fields (572→569, 570→673); HTML del feed trae 50 chips Evento / 37 links. Dedupe en vivo pendiente del primer ciclo post-deploy (worker demorado por VM saturada).
- Incidente paralelo: Postgres crash exit 2 01:03 UTC + recovery; 3er crash en 3 días. VM Docker al 1360% CPU crónico (host 6d sin reinicio). Load host 63→33.
