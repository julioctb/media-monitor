# field-reports-whatsapp

**Estado:** diseño consolidado y aprobado por Julio (22/oct 2026). Implementación NO iniciada — sin código escrito; este documento captura decisiones, no trabajo hecho.

## Objective

Tercera fuente del feed de media-monitor: reportes de campo cargados por personas en territorio vía bot de WhatsApp, con intake guiado, enriquecimiento LLM como intermediario (no aprobador), cola de revisión humana en admin, y publicación al feed. Mecanismo NUEVO desde cero: no se leen grupos existentes.

## Decisiones (cerradas)

1. **Canal: WhatsApp Cloud API** (no Telegram). Razón: adopción cero para gente de campo que ya usa WhatsApp. Costo verificado (Meta, pricing per-message desde jul-2025): mensajes entrantes de usuarios (service) gratis; respuestas free-form dentro de ventana 24h: primeras 1,000/mes por número gratis, después ~USD 0.0034 c/u (North America). Para el patrón "el humano escribe, el bot casi no responde" el costo operacional es ~0. Lo caro es el alta: verificación de business, webhook, token, método de pago en Meta Business.
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
Operador (WhatsApp) ──> Cloud API webhook ──> servicio whatsapp-webhook (compose, 5º svc)
    │                                            ├─ verificación firma X-Hub-Signature
    │                                            ├─ máquina de estados de conversación por número (intake guiado)
    │                                            └─ persist field_report (estado: draft)
    ──> enriquecimiento LLM (normaliza/dedupe/marca) ──> cola de revisión (admin UI)
    ──> aprobación humana ──> feed (tercera fuente, junto a RSS/scraper y social)
```

## Tasks tentativas (al arrancar; RED first donde aplique)

- [ ] T1 backend: modelo `field_reports` + `field_operators` (número, nombre, activo) + estado del reporte (`draft/review/published/rejected`). Diseño fino de schema pendiente al arrancar.
- [ ] T2 backend: servicio `whatsapp-webhook` en compose — verificación de firma, recepción idempotente (Meta reintenta), guardado draft. Cred Meta en `.env`, nunca commiteada.
- [ ] T3 backend: máquina de conversación del intake guiado (por número; timeout/reset de sesión).
- [ ] T4 backend: paso de enriquecimiento LLM (provider a definir; normaliza, clasifica, dedupe, flags) — escribe sugerencias, no cambia estado a published.
- [ ] T5 frontend: cola de revisión en admin — lista con identidad del operador, diff de lo sugerido por LLM, aprobar/editar/rechazar.
- [ ] T6 integración feed: reporte publicado entra al feed marcado como fuente `field`.
- [ ] Fase 2: fotos (media WhatsApp) y notas de voz + transcripción.

## Constraints

- No tocar el pipeline existente (RSS/scraper/X/FB) más allá del punto de publicación.
- Dominio de field reports aislado en su propio módulo (extracción futura barata).
- Número dedicado nuevo (no reutilizar líneas reconocibles); copy del bot neutro.
- Toda cred de Meta Business / tokens por `.env`; el webhook debe validar firma.

## Open points (resolver antes o durante implementación)

1. Atribución en el feed: rol/alias vs nombre.
2. Copy exacto del intake (preguntas y tono neutro).
3. Alta en Meta Business: quién la hace, chip dedicado, verificación.
4. Provider y costo del LLM de enriquecimiento (el enrichment chain existente puede reutilizarse).
5. Plan de session states: qué pasa si el operador abandone a media conversación.

## Route (al arrancar)

Por definir; historial del repo sugiere delegated writer (backend+frontend+tests) con suites completas y spot-check del parent. Comandos de verificación del repo: `.venv/bin/python -m pytest backend/tests -q` y `cd frontend && npm run check && npx vitest run && npm run build`.
