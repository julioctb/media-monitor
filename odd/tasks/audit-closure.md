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
- [x] T1 `scripts/audit_coherence.py` — 5 checks read-only del plan
- [x] T2 Corrida: 1 hallazgo real (`uncertain` sin mapear) → fix TDD
      `81d4aa4`; el resto OK (detalle: `AUDIT.md`).
- [x] T3 `AUDIT.md` con resultados, fix y validación final.
- [x] T4 pytest 427 / svelte-check 0 / vitest 61 / audit 5-5 OK.
- [x] T5 `83c820e` chore(audit) en `feat/visual-refresh` (merge: decisión usuario).

## Registro
- 2026-10-19: fase 3 ejecutada + cierre fase 4. 2 commits en
  `feat/visual-refresh` (81d4aa4 fix, 83c820e chore). Pendiente usuario:
  merge de la branch (11 commits visual + 2 audit).

## Verificación
- `.venv/bin/python -m pytest backend/tests -q` (esperado ≥370 passed)
- `cd frontend && npm run check` (0 errors) ; `npm test` (48+)
- `.venv/bin/python scripts/audit_coherence.py` → sin FINDINGS pendientes
  o documentados en AUDIT.md

## Ruta declarada
Inline direct. Justificación: un solo script nuevo read-only + reporte
generado; fixes contingentes acotados; el plan ya especifica métodos.
Riesgo verificación: medium (writer self-verify + spot check parent).
