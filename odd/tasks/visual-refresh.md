# Feature: visual-refresh — cierre de fidelidad vs mockups

## Objetivo
Completar la implementación visual del frontend (branch `feat/visual-refresh`)
hasta igualar la estructura de `referencia visual/*.html` (fuente de verdad,
8 pantallas). El primer pase (15:48–16:02) cubrió las 12 rutas a nivel archivo;
el usuario reporta cambios visuales incompletos.

## Estado
- Gap analysis: hecha (spec en el encargo).
- A resumen-diario: implementada (feat(digest)).
- B consultas: implementada (feat(consultas)).
- C feed: implementada (feat(feed)).
- D configuracion: implementada (feat(settings); keywords unificadas via KeywordsPanel + acciones compartidas, /keywords queda como ruta con la misma tabla).
- E shell+menores: implementada (nav con «Actores»; subnav solo para Alertas/Configuración; events 1 col + sample-note; events/[id] cardless; persons count/missing/footnote; persons/[id] profile-stat + hora «a las»).

## Verificación observada (parent spot check, 19/oct)
- `npm run check` → 0 errors, 0 warnings
- `npx vitest run` → 86/86 passed, 10 files
- `scripts/audit_coherence.py` → 5/5 OK
- `npm run build` ✔ (reportado por writer)
- Pendiente usuario: revisar UI y merge (branch con 17 commits).

## Verificación
- `cd frontend && npm run check && npx vitest run`
- `.venv/bin/python scripts/audit_coherence.py` (5/5 OK)

## Convenciones
- Los HTML de referencia visual/ son read-only.
- Commits convencionales por unidad; merge lo decide el usuario.
