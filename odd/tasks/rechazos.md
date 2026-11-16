# /rechazos: diseño e implementación de la cola de rechazos y aprobación manual

Estado: PENDIENTE (pedido Julio 16/nov). Trabajo en vuelo de la sesión de
embeddings en feat/embeddings (worktree unification): spec viva en
`odd/tasks/review-partial.md` (Sin commit alli) — ESE doc es la fuente
autoritativa; este archivo solo tracking y estado compartido.

## Specs

- S1 (verbatim Julio, 16/nov): "agrega como pendiente diseño e implementacion de / rechazos"
- S2 (verbatim Julio, origen de la feature — ver review-partial.md S1): "quiero que se publique lo aprobado, lo no aprobado se va a una seccion de revision, puede ser sobre la misma ruta de /rechazos y en esa seccion se debe poder hacer aprobacion manual"
- S3 Alcance: página /rechazos con (a) historial de rechazos
  (generation.review_rejections con reasons y snapshot) y (b) sección
  "Pendientes de aprobación" con approve/discard manual (review-partial S5/S6).
- S4 Paridad de diseño: el mockup MINE (referencia_visual/
  Panel-de-monitoreo-informativo) NO define página de rechazos — el diseño
  debe definirse (jerarquía, estados vacíos, copy) siguiendo el idioma visual
  del mockup antes de pulir implementación. Nav ya agregada (S2 de
  review-partial, DONE).

## Tasks

- [ ] T1 → S1,S4 | Diseño de la página /rechazos (estructura, estados, copy)
      sobre el idioma del mockup MINE; sin mockup propio, proponer y aprobar
      con Julio antes de implementar detalles visuales. Route: inline/parent.
- [ ] T2 → S2,S3 | Implementación: aterrizar el WIP de
      frontend/src/routes/rechazos/{+page.server.ts,+page.svelte} (load con
      rejections+pending, actions approve/discard) + actualizar el fixture
      del view test commiteado (hoy stale: 3 errores check, 2 fallos vitest).
      Gates: vitest + check 0/0 + build en feat/embeddings. Route: sesión
      embeddings (dueña del worktree).
- [ ] T3 → S2,S3 | Verificación end-to-end: cola visible, approve restaura
      snapshot con origin=revision_restore + fila de revisión, discard
      permanente, auditoría daily_summary_revision. Route: parent tras T2.

## Log

- L1 (16/nov, verbatim): "agrega como pendiente diseño e implementacion de / rechazos"
- L2 (16/nov): al crear este doc se detectó trabajo en vuelo — backend
  parcial DONE (review-partial T2/T3), frontend WIP sin commit, test fixture
  stale. Este doc NO compite: la spec autoritativa es review-partial.md.
