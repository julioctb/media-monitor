# Feature: digest-multi-cut — cortes múltiples del resumen diario

## Objetivo
El resumen diario se genera en **varios cortes del día** (ej. 08:00 y 21:00):
cada corte refresca el digest del día en curso (upsert idempotente). Si al
cambiar el día aún no hay datos, la home muestra la leyenda correspondiente
en vez de quedar vacía o mostrar el día anterior.

## Tareas
- T1 backend: migración + setting `digest_hours` (lista CSV, default `21`,
  valid 0-23, dedupe, al menos 1); `settings_runtime` y API schemas/update.
- T2 worker: `_digest_hours()`; scheduler sincroniza crons con la config
  (job resync cada 15 min: agrega/quita crons sin reiniciar); cada corte
  genera el digest del día en curso; si el día no tiene menciones, skip
  (no genera row vacío).
- T3 home: sin digest del día → bloque leyenda: «Todavía no se genera el
  resumen. Última actualización: <fecha larga + hora del summary más
  reciente>». Reemplaza el fallback que mostraba el digest anterior
  (commit f2acf21 se ajusta, no se borra su test sin reemplazo).
- T4 settings UI (Operación): editor de horarios (lista add/remove de horas,
  0-23) que persiste `digest_hours`; reemplaza el input único `digest_hour`
  (que queda como fallback de lectura para rows viejos).
- T5 tests backend+front y verificación completa.

## Estado
- T1 OK — commit `feat(digest): digest_hours setting with sorted-CSV storage
  and legacy fallback`. Migración `0020_digest_hours` (varchar(50) NOT NULL
  DEFAULT '21', backfill `digest_hours = digest_hour`), modelo, validator
  `queries._validate_digest_hours` (1..8 ints 0..23, dedupe, CSV ordenado),
  `settings_runtime.parse_digest_hours` + `EffectiveSettings.digest_hours`
  (digest_hour = primer corte), schemas Out/Update con validación.
  `upsert_settings` sincroniza digest_hour <-> digest_hours cuando se
  actualiza uno solo.
- T2 OK — commit `feat(digest): multi-cut worker schedule with 15m resync
  and empty-day skip`. Crons `digest_summary_<H>` por hora + job
  `digest_schedule_sync` cada 15 min (agrega/quita sin tocar otros jobs);
  `daily_summary_job` hace skip (return None, sin row) cuando el día no
  tiene menciones (window = day_window tz del cliente, mismo criterio que
  el builder).
- T3 OK — home sin fallback: `summary` es siempre el día pedido; sin digest
  el load expone `latest_updated_at` (updated_at del día más reciente vía
  getDailySummary(days[0]), null si no hay nada) y la leyenda muestra
  «Todavía no se genera el resumen del día» + «Última actualización».
- T4 OK — Operación: chips de hora (input 0..23 + X por chip, botón
  agregar, máx 8, mínimo 1) persistidos como `digest_hours`; el action
  dedupica y valida 1..8/0..23 con error 400 friendly.
- T5 OK — verificación abajo.

## Verificación
- `.venv/bin/python -m pytest backend/tests -q` → 439 passed (baseline 427).
- Migración up/down contra PG dev (`media-monitor-db-1`): 0019 → 0020 →
  0019 → 0020, backfill verificado (`digest_hours='21'`).
- Resync probado en vivo contra scheduler real + PG: boot deja
  `digest_summary_21`; con `digest_hours=8,21` agrega `digest_summary_8`;
  al volver a `21` lo remueve; el resto de los jobs no se tocaron.
- `npm run check` (0 errors), `vitest run` (92 passed), `npm run build` OK.
- Worker docker sin reiniciar (deploy a cargo del parent).

## Riesgos
- Worker vivo: el resync no debe duplicar jobs (ids fijos por hora) —
  cubierto por test de noop + probe en vivo.
- Rows viejos sin la columna → default '21' + backfill desde digest_hour.
