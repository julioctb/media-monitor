# agenda-page — Nueva página Agenda (calendar + CRUD manual)

**Contrato visual**: `referencia_visual/agenda-media-monitor.html` (self-contained mock; su
localStorage y su detección automática son placeholder explícito del mock — producción usa PG
y la detección queda fuera de este feature).
**Base**: `main` @ `1c62dc37`. Copy y orden EXACTOS del mockup.
**Autorización**: Julio, 23/oct: «la agenda es una feature nueva, creala».

## Alcance

- Tabla `agenda_items` (client-scoped): `id, client_id, title NOT NULL, kind activity|deadline,
  event_date DATE NULL, date_label TEXT NULL, time_label TEXT NULL, location, source, url, notes,
  created_at`. `event_date NULL` = «Sin fecha completa» (bucket con edición de fecha).
- API `/api/clients/{id}/agenda`: GET list, POST create (title único requerido), PATCH
  (edit-date promoción y edición completa), sin DELETE (el mockup no lo tiene).
- Página `/agenda` (route nuevo + nav entre Eventos y Actores, literal `href: '/agenda'` para
  audit_coherence):
  - intro h1 + «Añadir actividad» (dialog formulario: título req, kind select, date, time,
    location, source, url, notes) + link «resumen del día → /».
  - toolbar: búsqueda (título/lugar/fuente) + filtro (todas/actividades/plazos/fecha por
    confirmar).
  - «Actividades datadas» vista Calendario (mes navegable, day-detail al click) / Lista.
    «Sin fecha completa» + nota literal, con acción editar fecha (dialog: solo date; el resto
    se conserva).
  - Empty state «No hay actividades para mostrar».
  - Nota del mock sobre localStorage/producción: OMITIR (describes el mock, no el producto);
    help de «año actual» OMITIR (es de detección, no construida).
- Sin detección automática ni seed: inicia vacío.

## Tareas

- [ ] **T1 backend**: model + migration 0022 + queries + router `api/agenda.py` + schemas +
      tests (CRUD + validación title + client scope). RED→GREEN.
- [ ] **T2 front data+server**: tipos/fns en `lib/api.ts`; `+page.server.ts` load + actions
      create/edit-date (patrón settings: enhance, errorStatus/ErrorMessage); server test del
      payload.
- [ ] **T3 front página**: estructura completa mockup-fiel (intro/toolbar/lista/undated/forms
      como bloques condicionales, no `<dialog>`); card `.activity` anatomy; filtros client-side.
- [ ] **T4 calendar**: grid mensual, nav mes, day-detail, toggle lista.
- [ ] **T5 verificación integral + nav**: view test, `npm run check && vitest && build`,
      pytest, audit_coherence (nav literal), deploy api+dashboard, verificación de snapshot y
      SSR.

## Verificación

- Backend: `.venv/bin/python -m pytest backend/tests -q`
- Front: `cd frontend && npm run check && npx vitest run && npm run build`
- Coherencia: `.venv/bin/python scripts/audit_coherence.py`
