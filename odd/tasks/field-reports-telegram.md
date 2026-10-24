# field-reports-telegram

**Estado:** diseño consolidado y aprobado por Julio (22/oct 2026). Canal
cambiado de WhatsApp a **Telegram** (23/oct 2026, decisión de Julio) — el
core del diseño no cambia, solo el transporte; el análisis de WhatsApp
queda abajo como registro de la decisión descartada. Implementación NO
iniciada — sin código escrito.

## Objective

Tercera fuente del feed de media-monitor: reportes de campo cargados por personas en territorio vía bot de WhatsApp, con intake guiado, enriquecimiento LLM como intermediario (no aprobador), cola de revisión humana en admin, y publicación al feed. Mecanismo NUEVO desde cero: no se leen grupos existentes.

## Decisiones (cerradas)

1. **Canal: Telegram Bot API** (cambio 23/oct; antes WhatsApp Cloud API). Razón: misma adopción cero para gente de campo, sin fricción de alta — bot en BotFather en minutos, sin verificación de business ni método de pago; bots gratis (sin contadores ni ventanas 24 h). **Long polling en vez de webhook**: sin URL pública, sin HTTPS, sin firma — un proceso del compose pregunta por mensajes. Además teclados de respuesta nativos para el intake guiado. Único requerimiento: token del bot en `.env`. El análisis de WhatsApp (costos Cloud API, alta Meta) queda al final como registro.
2. **Intake guiado, no texto libre**: el bot conduce el reporte por preguntas (qué pasó / dónde / cuándo / nota opcional). Datos semi-estructurados desde el origen; el parsing se hace barato.
3. **LLM intermediario, NO portero**: normaliza texto, clasifica, deduplica contra lo ya publicado, marca inconsistencias ("esta obra cerró el martes según nota X"). No aprueba solo: un LLM sin fuente verificable no es árbitro de hechos; su valor es estructurar y cruzar.
4. **Cola de revisión humana** antes del feed. Un reporte de campo mal cargado contamina el feed igual que una noticia falsa.
5. **Anonimato UNIDIRECCIONAL** (aclaración de Julio: "anónimo nada más para ellos, yo sí debo saber"):
   - Hacia ellos: marca neutra del bot ("Reportes de Campo" o similar), número dedicado NO reconocible (ni personal ni de oficina), links genéricos o ninguno, copy neutro (no tono institucional). Ellos no saben quién administra ni quién lee.
   - Hacia Julio: identidad plena en admin — número real, nombre si está disponible, historial de reportes. Sin hash ni pseudonimización; mapping número→operador en tabla interna.
   - Atribución visible en el feed (rol/alias vs nombre): POR DECIDIR al ver el feed armado.
6. **Hogar: dentro de media-monitor.** El webhook receiver es un servicio más del `docker-compose.yml`; la cola de revisión es una sección admin más. Razones: el destino de la cola ES el feed (misma DB, cero sync), el patrón worker/compose ya existe, un solo deploy. Tradeoff aceptado: acoplamiento — mitigar manteniendo el dominio (reporte/revisión/publicación) aislado en su propio módulo para extracción futura barata.
7. **Multimedia en fase 2**: fotos y notas de voz (con transcripción) después del núcleo text+flujo, para no inflar el primer slice.

## Arquitectura prevista

```
Operador (Telegram) <──long polling── bot worker (compose, svc dedicado o thread del worker)
    │                                      ├─ máquina de estados de conversación por chat id (intake guiado, reply keyboards)
    │                                      └─ persist field_report (estado: draft)
    ──> enriquecimiento LLM (normaliza/dedupe/marca) ──> cola de revisión (admin UI)
    ──> aprobación humana ──> feed (tercera fuente, junto a RSS/scraper y social)

Nota: sin webhook ni URL pública; el bot hace getUpdate s long-poll contra
telegram. El servicio de WhatsApp+Cloud API (5° svc con firma X-Hub) quedó
descartado con el cambio de canal.
```

## Tasks tentativas (al arrancar; RED first donde aplique)

- [ ] T1 backend: modelo `field_reports` + `field_operators` (número, nombre, activo) + estado del reporte (`draft/review/published/rejected`). Diseño fino de schema pendiente al arrancar.
- [ ] T2 bot: polling worker de Telegram (`getUpdates` long-poll) — idempotencia por update_id, token en `.env`, nunca commiteada. Sin URL pública ni webhook.
- [ ] T3 bot: máquina de conversación del intake guiado (por chat id; timeout/reset de sesión; reply keyboards por paso).
- [ ] T4 backend: paso de enriquecimiento LLM (provider a definir; normaliza, clasifica, dedupe, flags) — escribe sugerencias, no cambia estado a published.
- [ ] T5 frontend: cola de revisión en admin — lista con identidad del operador, diff de lo sugerido por LLM, aprobar/editar/rechazar.
- [ ] T6 integración feed: reporte publicado entra al feed marcado como fuente `field`.
- [ ] Fase 2: fotos (media WhatsApp) y notas de voz + transcripción.

## Constraints

- No tocar el pipeline existente (RSS/scraper/X/FB) más allá del punto de publicación.
- Dominio de field reports aislado en su propio módulo (extracción futura barata).
- Número/chat dedicados; copy del bot neutro. Token de Telegram por `.env`.

## Open points (resolver antes o durante implementación)

1. ~~Atribución en el feed: rol/alias vs nombre~~ DECIDIDO (23/oct): **nombre del operador** — ya es el comportamiento: `publish_field_report` pone `author = display_name` y `MentionCard` lo muestra en la fuente. Sin cambios de código.
2. Copy exacto del intake (preguntas y tono neutro).
3. ~~Alta en Meta Business~~ Token del bot: crear con BotFather (2 min), pegar en `.env`. Sin verificación ni método de pago.
4. Provider y costo del LLM de enriquecimiento (el enrichment chain existente puede reutilizarse).
5. Plan de session states: qué pasa si el operador abandone a media conversación.

## Route (al arrancar)

Por definir; historial del repo sugiere delegated writer (backend+frontend+tests) con suites completas y spot-check del parent. Comandos de verificación del repo: `.venv/bin/python -m pytest backend/tests -q` y `cd frontend && npm run check && npx vitest run && npm run build`.
