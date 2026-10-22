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

- [ ] T0 — branch `feat/fb-public-ingest` + este doc
- [ ] T1 — dependencia Playwright (pyproject + install local + Dockerfile)
- [ ] T2 — fixture HTML real `backend/tests/fixtures/facebook_page_public.html`
- [ ] T3 — parser puro `extract_posts` (TDD contra fixture)
- [ ] T4 — `to_raw_mentions` + `FacebookPublicAdapter` (TDD, sin red)
- [ ] T5 — settings sin token: `FacebookPageTarget`, config/schemas/queries/worker
- [ ] T6 — frontend y probe fuera (`test-facebook` dado de baja)
- [ ] T7 — smoke en vivo (docker build/up + adapter aislado + ciclo worker + UI)
- [ ] T8 — eliminar camino Graph (`facebook_page.py`, tests, referencias)
- [ ] T9 (docs) — README + evidencia en este doc; sin push

## Evidencia / notas de ejecución

(registradas al avanzar)

## Lecciones

(al cierre)
