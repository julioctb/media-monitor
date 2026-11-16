# Feature: digest editorial para rectora (digest v2)

Plan aprobado: `.hermes/plans/2026-10-18_160856-digest-editorial-rectora.md` (2026-10-18).
User OK: "ejecuta".

## Objetivo
Digest diario programado con estructura editorial (noticias por eje, rectora,
redes, personas, confianza, pendientes) en la home, schema JSON v2 estable para
LLM/RAG, alimentado por events/persons/classifications y consumido por ask.

## Veredicto alineamiento
La arquitectura actual alinea; falta capa editorial. El paste del tick 17 oct
mapea 1:1 a datos existentes (ver tabla en el plan). Sin tablas ni endpoints
nuevos: `daily_summaries.content` pasa a `schema: 2`.

## Tareas
- [x] T1 settings `digest_hour` (modelo+0018+runtime+worker+test)
- [x] T2 `summaries/digest.py` schema v2 + `validate_digest` (test)
- [x] T3 `build_digest_facts` determinista (test)
- [x] T4 `confidence_for` / `gaps_for` (test)
- [x] T5 composer en `builder.py`: LLM acotado + fallback, content v2, plain_text
- [x] T6 frontend `DigestSections` + home hero + summary v2 (test vitest)
- [x] T7 `ask.build_context` prioriza digest reciente (test)
- [x] T8 deploy compose + verificación end-to-end (schema==2 en API, home render)

## Route / verificación
- Route: inline (plan ultra-especificado, tareas bite-sized, sesión con contexto
  cargado). Verification: self por tarea (medium) + parent spot check final.
- Commands: `cd backend && ../.venv/bin/python -m pytest tests -q`;
  `cd frontend && npm run check && npx vitest run`.
- Delivery: work-unit commits sobre `feat/scraper-ingest`; push/PR decide Julio.

## Estado
- T1-T8 OK. Commits: cb390bf (digest_hour), b2b9ac7 (api settings), c73af64
  (schema v2), ed458d4 (rules), 358e4f8 (facts), b3165ab (composer v2 +
  focus person 0019), cf01985 (frontend), 2727426 (ask), 60b6fe4 (fix
  person_ids: person_links son MentionPerson; el id vive en link.person_id).
- Suite 411 passed; svelte-check 0; vitest 59.
- Deploy verificado en vivo (2026-10-18): migraciones 0018/0019 aplicadas;
  POST generate -> schema 2 con las 8 secciones (11 noticias / 13 personas);
  GET por fecha OK; hero en / con link a /summary; RECTORA con focus person 4
  (María Lilia Cedillo) -> 16 oct: 5 menciones tone positive.
- Config live: digest_focus_person_id=4 via PUT /api/settings.
- Nota para después: menciones scraper sin published_at no entran a ninguna
  ventana de digest (behavior v1 del day-window); el ingest debería
  fallback a ingested_at. Fuera de scope de este feature.

## Cierre 16/nov (auditoría de obsolescencia) — COMPLETA vía digest v3/v3.1

Toda la feature aterrizó por otras vías: T1 `digest_hour` (evolucionó a
multi-cut `digest_hours`, settings_runtime.py:38-41); T3/T4
`build_digest_facts` + `confidence_for`/`gaps_for` (digest.py:99,108); T5
composer v3 con fallback heurístico sobre el mismo esqueleto; T6
`DigestSections.svelte` en producción; T8 desplegado (digests v3 sirviéndose).
T2 SUPERSEDA: schema v2 → v3.1 (digest_schema.py). Feature absorbida por
digest-brief-v3 + multi-cut.
