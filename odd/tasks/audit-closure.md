# Feature: audit-closure — cierre Auditoría integridad y coherencia

## Objetivo
Ejecutar la Fase 3 (coherencia cross-capa scripted) y el cierre de la Fase 4
del plan `~/.hermes/plans/2026-10-14_152147-auditoria-integridad-coherencia.md`,
que quedó a mitad de camino el 14/oct (fixes aplicados, sin script, sin
reporte, sin re-validación final).

## Estado previo verificado (2026-10-19)
- Fases 0–2 + fixes parciales: commits 14/oct 16:34–18:06 en main.
- NO existe `scripts/audit_coherence.py`, ni `AUDIT.md`, ni registro de
  re-validación final.
- Branch actual: `feat/visual-refresh` (11 commits sin merge, decisión del
  usuario). La auditoría corre sobre este checkout: es el código que va a main.

## Tareas
- [ ] T1 `scripts/audit_coherence.py` — 5 checks read-only del plan
      (routes↔nav, enums clasificación, contrato TS↔pydantic, labels DB,
      env/config). Read-only; salida `OK`/`FINDINGS` por cheque.
- [ ] T2 Correr script; clasificar hallazgos: objetivo-trivial → fix TDD +
      commit `fix(<área>): ...`; juicio/diseño → sólo AUDIT.md.
- [ ] T3 `AUDIT.md` raíz del repo: resultados por fase, hallazgos, 
      `Pendientes de decisión`.
- [ ] T4 Validación final del plan: pytest backend, svelte-check, vitest,
      re-run audit script OK. (build si el tiempo lo permite)
- [ ] T5 Commit work-unit: `chore(audit): coherence script + report`.

## Verificación
- `.venv/bin/python -m pytest backend/tests -q` (esperado ≥370 passed)
- `cd frontend && npm run check` (0 errors) ; `npm test` (48+)
- `.venv/bin/python scripts/audit_coherence.py` → sin FINDINGS pendientes
  o documentados en AUDIT.md

## Ruta declarada
Inline direct. Justificación: un solo script nuevo read-only + reporte
generado; fixes contingentes acotados; el plan ya especifica métodos.
Riesgo verificación: medium (writer self-verify + spot check parent).
