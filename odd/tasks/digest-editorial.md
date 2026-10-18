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
- [ ] T1 settings `digest_hour` (modelo+0018+runtime+worker+test)
- [ ] T2 `summaries/digest.py` schema v2 + `validate_digest` (test)
- [ ] T3 `build_digest_facts` determinista (test)
- [ ] T4 `confidence_for` / `gaps_for` (test)
- [ ] T5 composer en `builder.py`: LLM acotado + fallback, content v2, plain_text
- [ ] T6 frontend `DigestSections` + home hero + summary v2 (test vitest)
- [ ] T7 `ask.build_context` prioriza digest reciente (test)
- [ ] T8 deploy compose + verificación end-to-end (schema==2 en API, home render)

## Route / verificación
- Route: inline (plan ultra-especificado, tareas bite-sized, sesión con contexto
  cargado). Verification: self por tarea (medium) + parent spot check final.
- Commands: `cd backend && ../.venv/bin/python -m pytest tests -q`;
  `cd frontend && npm run check && npx vitest run`.
- Delivery: work-unit commits sobre `feat/scraper-ingest`; push/PR decide Julio.

## Estado
- (en curso)
