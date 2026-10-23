# Feature: x-mode-settings — switch modo X (gratuito/pago) + API key en Configuración

## Objective
En Configuración, controlar la fuente de X desde la UI: switch de modo **Gratuito** (x_index vía índice de Google News, implementado en x-index-source) vs **API de pago** (twitter_x.py / twitterapi.io-compatible), con campo para guardar la API key y texto de limitaciones del modo gratuito.

## Problem
Hoy x_index corre incondicional y el adapter pago solo se activa con X_PROVIDER_API_KEY (env, vacío) — no hay control desde la UI y la key no tiene dónde guardarse.

## Why
Julio lo pidió (22/oct): switch que respete el diseño + campo para la API + texto de modo gratuito con limitaciones + eliminar código muerto del camino viejo.

## Design decisions (orquestador)
1. `x_mode`: `'free'` (default) | `'paid'` — excluyentes. free → XIndexAdapter; paid → TwitterApiIoProvider con key de settings.
2. `x_api_key`: columna en settings. PUT: string no-vacío guarda; string vacío NO cambia (conserva). GET: NUNCA devuelve la key — expone `x_api_key_set: bool` y `x_api_key: ""` (masking, el front no necesita leerla).
3. paid sin key → `log.warning` + fallback a x_index (la cobertura nunca se pierde en silencio).
4. Env `X_PROVIDER_API_KEY` MUERE (código muerto): config.py, branch env en worker.py. `X_PROVIDER_BASE_URL`/rate se quedan en config como defaults del proveedor.
5. Limitaciones del modo gratuito (copy UI, español): sin handle de autor (anónimo); cobertura = lo que Google indexa (medios y cuentas institucionales, no toda la conversación); detección diferida al índice (no tiempo real).
6. UI copy español; código/comentarios/identificadores inglés. Sin modo "off" (no pedido).

## Scope
- Backend: settings chain completa (models/settings.py 2 columnas, migración alembic dialect-agnostic, settings_runtime.py, queries.py validators, schemas Out/Update + masking, endpoint PUT), worker.build_adapters re-wiring free/paid+fallback, config.py dead path removal.
- Frontend: sección en Configuración (switch modo según mockup, campo key con hint "dejar vacío para conservar la actual", texto limitaciones cuando free, estado key guardada), server action wiring, tests.
- Deploy: api+worker+dashboard (front cambió).

## Constraints
- Mockup `referencia_visual/configuracion-media-monitor.html` es el contrato: extraer TODAS las reglas del elemento switch/panel antes de maquetar (skill media-monitor-dev).
- No tocar cambios no commiteados de Julio. Commits conventional español, pathspecs propios. Branch `feat/x-mode-settings` desde `feat/x-index-source` (depende del adapter x_index).
- Migración: reglas alembic del skill (dialect-agnostic, BigInteger variant); db container es dev Y prod.
- Formularios SvelteKit: reglas del skill (use:enhance, reset:false, getAll por input nuevo).

## Tasks
- [ ] T1 — Backend: columnas + migración + settings chain + worker free/paid+fallback + dead path env + masking + tests (RED→GREEN). Commit feat.
- [ ] T2 — Frontend: sección Configuración según mockup + action wiring + tests (check + vitest). Commit feat.
- [x] T3 — Deploy 3 servicios + verificación: PUT round-trip (x_mode paid + key, GET sin key expuesta, vacío conserva), ciclo logs (`adapter x_twitter` con key dummy inválida → warning fallback `adapter x_index`), UI sirve. Orquestador. → completado (ver evidence); el ciclo live corrió en free (default); el camino paid-live queda para cuando Julio cargue su key real.

## Verification evidence
- 2026-10-22/23 (T3, orquestador): build 3 imágenes OK; `alembic upgrade head` → `0021` con columnas `x_mode`/`x_api_key` en PG; GET `/api/settings` → `x_mode`+`x_api_key:''`+`x_api_key_set` (key nunca serializada); round-trip PUT paid+key → `x_api_key_set:True`, PUT free → key conservada (fila DB: `free | dummy-roundtrip-9f3` — dummy inertes, reemplazar desde UI); `/settings` sirve action `save-x` + placeholder + banner; worker recreado con snapshot nuevo cicla en free (`adapter x_index: fetched 1, inserted 1` 02:37 UTC). Front: 119 vitest + check + build (writer). Back: 442 pytest (spot check orquestador).
- Nota: writer T1 original (sesión paralela) murió por 429 del pool GLM tras commit T1; T2 re-delegado y completado.

## Progress log
- 2026-10-22: doc creado; diseño decidido; implementación T1+T2 delegada.
- 2026-10-22 (noche): corrección de ubicación a pedido de Julio — la sección X vive DENTRO de Fuentes como `article.source-card--wide` entre «Redes sociales» y «Datos de campo» (`c198d72b`); el form owner `x-save-form` queda a nivel página y los inputs se asocian vía `form=` (HTML5) porque el grid de Fuentes vive dentro del form principal `?/save` y anidar forms es inválido. Nav sin ancla X (queda bajo Fuentes). check 0/0, 119 vitest, build OK; dashboard redeploy + verificación de HTML servido en curso.
- Espejo Engram (topic `odd/x-mode-settings/tasks`): PENDIENTE — mem_save no disponible en esta sesión.
