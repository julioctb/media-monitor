# Auditoría de integridad y coherencia — media-monitor

Plan: `~/.hermes/plans/2026-10-14_152147-auditoria-integridad-coherencia.md`.

## Estado de ejecución

| Fase | Alcance | Estado |
|------|---------|--------|
| 0 Baseline | repo limpio, suite base | OK 14/oct (commits 16:34–18:06) |
| 1 Inventario de verdad | routes/models/routers | OK 14/oct |
| 2 Smoke por página | HTML markers + API probes | OK 14/oct (sin reporte persistido) |
| 3 Coherencia scripted | `scripts/audit_coherence.py` | OK 19/oct (esta corrida) |
| 4 Hallazgos → fixes | 1 fix objetivo; juicio→reporte | OK 19/oct |

Nota honesta: la corrida del 14/oct no dejó reporte; la evidencia son los
commits de fixes de esa tarde. La fase 3 quedó sin ejecutar hasta hoy.

## Resultados Fase 3 (2026-10-19, checkout `feat/visual-refresh`)

```
[OK] 1. routes <-> nav            (10 rutas estáticas en nav; /events/[id] y
                                   /persons/[id] son detalle, enlazadas desde
                                   listas — sin entrada de nav por diseño)
[OK] 2. enums clasificacion       9/9 topics con label+badge en TS
[OK] 3. contrato TS<->pydantic    Mention, PersonSummary, PersonTimelineItem,
                                  AskResult: sin asimetrías
[OK] 4. labels DB vs mapas TS     topic 8/8, political 3/3 mapeados;
                                  'topics' enrichment: 638 labels free-form,
                                  se renderizan crudos (sin mapa, por diseño)
[OK] 5. env/config                API_BASE_URL consistente (.env.example =
                                  fallback api.ts); 1 cliente con ai_api_key
```

Re-ejecutable: `.venv/bin/python scripts/audit_coherence.py`
(requiere docker con el contenedor `media-monitor-db-1` arriba para 4 y 5).

## Fixes aplicados (Fase 4)

- `fix(ui): map uncertain political label` — `uncertain` (classifier
  `political`) vivía en DB sin entrada en `CLASSIFICATION_LABELS`
  (`frontend/src/lib/format.ts`); caía al fallback raw. Mapeado a
  `Sin clasificar` + test de anclaje en `format.test.ts` (RED→GREEN
  verificado).

## Pendientes de decisión (sin tocar)

- Ninguno nuevo. Las páginas de detalle sin entrada de nav son intencionales;
  los labels `topics` del enrichment se muestran crudos por diseño.

## Validación final (2026-10-19)

```
.venv/bin/python -m pytest backend/tests -q   -> 427 passed
cd frontend && npm run check                  -> 0 errors, 0 warnings
npx vitest run                                -> 61 passed (7 files)
scripts/audit_coherence.py                    -> 5/5 OK
```
