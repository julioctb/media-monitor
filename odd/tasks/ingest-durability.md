# Feature: ingest-durability — monitoreo con memoria (media-monitor)

## Objetivo
Que la ingesta opere como analista con memoria: corte incremental por fuente,
ledger de corridas con gaps explícitos, estado durable en Postgres y dedupe
por evento canónico. Objetivo completo redactado por el usuario (7 puntos);
este feature lo aterriza al código en `backend/app/`.

## Problema (gap analysis, 13 oct 2026)
- Adapters fetch "lo reciente" sin cursor persistido: cada corrida re-barre la
  misma ventana y una fuente caída no acumulo deuda visible.
- Falla de adapter → `stats[adapter]=0` + log; sin registro durable, el panel
  no distingue "sin noticias" de "fuente caída".
- Dedupe actual: solo `url_hash` por mención (queries.insert_mention). No hay
  evento canónico: sindicaciones/rewrites acumulan menciones duplicadas.
  (verificado en `app/ingest/pipeline.py`, `app/worker.py`, `app/models/queries.py::insert_mention`)

## Alcances

### Fase 1 — Higiene de ingesta (esta sesión)
- T1 [x] Modelo `IngestCursor` (client_id, adapter_name, last_success_at,
  overlap_min) + migración Alembic siguiendo el patrón de `backend/migrations/`.
- T2 [x] Cursor en el ciclo: `run_ingest_cycle` lee cursor por adapter, pasa
  `since` a `SourceAdapter.fetch` (param opcional con default None; adapters
  que no puedan filtrar lo ignoran). Avance SOLO en éxito:
  `last_success_at = cycle_started`. Estado en Post, sobrevive reinicios.
- T3 [x] Ledger `IngestRun` (cycle_started, client_id, adapter_name, status
  ok|error, items_seen, inserted, error, duración) — una fila por adapter por
  ciclo; failure → status=error + texto de excepción. Endpoint GET
  `/ingest/runs` (últimas corridas por adapter) para visibilidad de gaps.
- T4 [ ] Tests: cursor no avanza en falla; gap quedará registrado; idempotencia
  de re-ingesta; endpoint. Suite completa verde.

### Fase 2 — Evento canónico (sesión futura, requiere decisión de diseño)
- T5 [ ] Modelo `Event` + clustering de menciones (similitud título + ventana
  temporal + mismas entidades) en pipeline post-dedupe url_hash.
- T6 [ ] Alerts/digests y panel consumen eventos, no menciones crudas.
- DECISIÓN PENDIENTE (usuario): schema nuevo + cambios de API/panel — definir
  antes de implementar.

## Verificación
- `.venv/bin/python -m pytest backend/tests -q` (baseline 13 oct: 217 passed)
- `alembic upgrade head` contra dev PG al aplicar (media/media)

## Convenciones
- Rama feature `feat/ingest-durability`; work-unit commits Conventional
  Commits, sin co-authored-by. Push/merge: decisión del usuario.
- Adapters siguen transport-only (contrato en `app/ingest/base.py`).
- Progreso: actualizar este archivo + espejo Engram tras cada tarea.

## Registro
- 2026-10-13: creado tras exploración (pipeline.py/worker.py/queries leídos).
  Fase 1 delegada a writer; verificación media (suite tests + migración).
