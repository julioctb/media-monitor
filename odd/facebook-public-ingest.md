# Facebook public ingest (sin tokens) — checklist de ejecución

Plan fuente: `~/.hermes/plans/2026-10-22_150350-facebook-tokenless-ingest.md` (aprobado 2026-10-22). Branch: `feat/fb-public-ingest`. Un commit Conventional por tarea, sin co-authored-by, sin push (Julio decide push/PR).

## Objetivo

Reemplazar la ingesta de Facebook basada en Graph API + tokens por un adapter que scrapea páginas públicas con Playwright (Chromium headless), y eliminar el código muerto que la dependencia de tokens deja atrás (`FacebookPageCredentials` con `token`/`kind`, probe `test-facebook`, `fb_graph_api_version`, `FB_PAGES` con tokens).

Motivación verificada: el token de Graph solo lee páginas propias (`pages_read_engagement`); terceras páginas exigen PPCA + App Review + verificación de negocio (errores `#10`/`#100` del 2026-10-22). Scraping HTTP simple descartado con evidencia: `www`/`mbasic`/`m.facebook.com` devuelven solo shell JS — hace falta navegador headless.

## Arquitectura

- `backend/app/ingest/facebook_public.py`: `extract_posts(html)` (parser puro, testeado contra fixture real), `to_raw_mentions(...)`, `FacebookPublicAdapter` (1 Chromium headless por ciclo, `div[role="article"]`, primeros N posts).
- `FacebookPageTarget(page_id, label)` reemplaza `FacebookPageCredentials`; pydantic v2 ignora `token`/`kind` viejos en la fila de settings → sin migración.
- Timestamp: `data-utime` (epoch) primario; label relativo («hace 2 h») fallback; `None` si nada (el digest tolera `published_at` NULL vía watermark de ingesta).
- Logged-out solo renderiza la primera pantalla de posts: suficiente para ciclo incremental de 15 min, no para backfill.

## Checklist

- [x] T0 — branch `feat/fb-public-ingest` + este doc (`a434b292`)
- [x] T1 — dependencia Playwright (pyproject + install local + Dockerfile) (`0cfadeb8`)
- [x] T2 — fixture HTML real `backend/tests/fixtures/facebook_page_public.html` (`2763aa83`)
- [x] T3 — parser puro `extract_posts` (TDD contra fixture) (`dc2d3221`)
- [x] T4 — `to_raw_mentions` + `FacebookPublicAdapter` (TDD, sin red) (`ffbc56a0`)
- [x] T5 — settings sin token: `FacebookPageTarget`, config/schemas/queries/worker (`13b17e68`)
- [x] T6 — frontend y probe fuera (`test-facebook` dado de baja) (`0db3833e`)
- [x] T7 — smoke en vivo (docker build/up + adapter aislado + ciclo worker + API)
- [x] T8 — eliminar camino Graph (`c7a845c9`)
- [x] T9 (docs) — README + este doc; sin push (Julio decide push/PR)

## Evidencia / notas de ejecución

- T2 (fixture): captura estable de `https://www.facebook.com/105335348671635/` (`Despierta BUAP`, sin login-wall). Hallazgos del DOM real 2026-10-22:
  - Los permalinks vienen como `permalink.php?story_fbid=pfbid...&id=...` — NO existe `/posts/|/permalink/|/videos/` en el HTML público (0 ocurrencias).
  - Sin `data-utime`, sin `<time>`, sin `data-testid`. Timestamp solo como `aria-label` de fecha en el anchor del permalink («8 de septiembre de 2025», sin hora) → `created_at` queda `None` salvo utime/relativo (R3 asumido).
  - El muro logged-out renderiza 1 post real (4 divs `role="article"` anidados: post + comentarios); estable tras scrolls/networkidle.
- T3: el fixture no tiene `data-utime` ni labels relativos → `created_at=None` (ruta cubierta con HTML sintético en tests; R3 asumido). El muro anida el post y su artículo de comentarios con el mismo `story_fbid` pero query distinto → dedupe por `external_id`, no por URL cruda.
- T7 (smoke, 2026-10-22):
  - Build api+worker con la capa nueva `playwright install --with-deps chromium`; `docker compose up -d` recreó api/worker; código nuevo verificado dentro del contenedor (`grep FacebookPublicAdapter /srv/backend/app/ingest/facebook_public.py` → 1).
  - Smoke aislado en `worker`: `FacebookPublicAdapter([{page_id}]).fetch(["BUAP"])` → `ROWS: 1`, permalink `permalink.php?story_fbid=pfbid0Hti...&id=100079570931347`, título «Temporada de Zopilotes…», `published None` (esperado).
  - `PUT /api/settings {"facebook_pages": [{"page_id": "105335348671635", "label": "Despierta BUAP"}]}` → persistido sin token.
  - Ciclo 21:46:37 UTC: `adapter facebook_page: fetched 1 items, inserted 0 new mentions` — sin `facebook public ... failed`. `inserted 0` = watermark sobre post de 2025-09-08 (comportamiento documentado); las menciones fb previas (903/904, autor «Despierta BUAP») sirven la misma ruta API/UI.
  - DB: `SELECT ... WHERE source='facebook_page'` → 2 filas con autor correcto; API `/api/mentions` las sirve.
- T8: `grep` final limpio — solo quedan `MentionSource.facebook_page` (enum, valor en DB), el string `"facebook_page"` (logs) y el fallback env `FB_PAGES` vivo en `settings_runtime`. Sin `FB_PAGES` en compose/.env.

## Lecciones

- El HTML público logged-out de Facebook (2026-10-22) no tiene `data-utime`, `<time>` ni `data-testid`: el timestamp hay que tomarlo de `aria-label` de fecha o entrar sin él; los permalinks vienen como `permalink.php?story_fbid=...`, no `/posts/`.
- El muro público anida el artículo del post y artículos de comentarios que repiten el permalink con query distinta: deduplear por id estable (`story_fbid`), nunca por URL cruda.
- Playwright en contenedor necesita la capa `playwright install --with-deps chromium` DESPUÉS del `pip install .` en el Dockerfile; el binario pesa ~100 MB y vive en el cache de imagen, no en la venv.
- pydantic v2 ignora claves extra al hidratar modelos: la fila legacy de settings con `token`/`kind` se convierte a `FacebookPageTarget(**entry)` sin migración.
- `inserted 0 new mentions` en el primer ciclo tras activar una fuente es normal si el watermark cubre los items viejos: la señal de éxito es `fetched N`, no el insert.
