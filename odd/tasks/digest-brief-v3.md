# Digest v3.1: esqueleto determinístico + brief/evidencia + campo

Estado: PR1+PR2 COMPLETOS Y VERIFICADOS (25/oct); T6 marcada en doc 16/nov
tras verificación: 920fa81a es ancestro de feat/digest-brief-v3 (rama UI
stacked ya fusionada), focused vitest 21/21 (DigestV3 + digest-v3).
ENTREGA RESUELTA 16/nov (decisión Julio): sin PR — push de respaldo de la
rama + fast-forward de main a 1457113b (origin/main = origin/feat/digest-brief-v3 = 1457113b;
incluye los 2 commits pre-existentes de main). Gates previos: backend 1450
passed, svelte-check 0/0, vitest 360/360 (2 fixtures de fecha vencidos en
home-page.server.test.ts corregidos a meses relativos, commit 1457113b),
build OK. Asses nativo del rango 3905ceff..1457113b: riesgo medio, reviewDue
false (under_budget), auto-verificación del escritor. Pushear no despliega
(producción corre desde otro worktree con imágenes baked).

## Problema (verificado en DB, 25/oct)

1. Síntesis re-cuenta en vez de delta; jerarquía por volumen y no por impacto
   (Lobos Puebla al nivel de la reforma pensionaria).
2. `redes` es anexo, no teje señal en la narrativa. Instagram 24-oct count 0.
3. `field_reports` ausente del digest. DB: 5 reportes, 0 published, 4 rejected,
   1 review.

## Diseño cerrado — esqueleto determinístico, LLM solo prosa y criterio

Principio: el código construye TODO lo derivable; el modelo solo sintetiza prosa
y jerarquiza. Un solo schema: el modo heurístico y el LLM llenan el mismo
esqueleto → un solo camino de render.

- **CÓDIGO (determinístico, testeable):** delta (diff de eventos vs summary del
  día hábil previo); tarjetas por historia (agrupación existente evento+sources)
  con tono agregado y repeat; sección campo (published siempre; review marcado
  "en revisión" — decidido con Julio); fechas por regla (caducó si fecha<=hoy;
  próxima<=7 días); esqueleto del brief con secciones FIJAS.
- **LLM (1 llamada, output chico ~400 tokens):** por historia `hecho` (1 oración)
  + `por_que` (1 oración); brief: `headline` + selección por ÍNDICE
  `[{index, categoria decision|ruido|a_favor, razon_corta}]` referenciando
  tarjetas existentes (el modelo no inventa estructura).
- **Contrato:** el detalle nunca opina; el brief no introduce datos fuera del
  esqueleto; degradación por campo (sin por_que la tarjeta renderiza igual;
  fallback heurístico = mismo documento sin prosa, titular por impacto
  computado). Prosa en español editorial: la CALIDAD escala con el modelo
  (DeepSeek, GLM Spark, Gemini), la estructura es fija.
- **Routing por roles — fase POSTERIOR, NO en PR1:** `analysis` (API premium),
  `extract` (GLM local), `embedding` (Qwen, con dedupe-v2). Regla volumen×juicio.
  Feature doc aparte al cerrar PR1. Nodo Spark A al 98% de memoria (119/121GB,
  medido 25/oct): NO colocalizar embeddings con glm53-flash-tf; CPU Mac u otro
  destino.

## Entrega en 2 PR

- **PR1 (backend): T1-T5.** Queda usable por API/regeneración; dashboard actual
  convive (T4 compat).
- **PR2 (frontend): T6.** Render brief + tarjetas + campo.

## Tasks PR1 (backend) — COMPLETAS 25/oct, branch feat/digest-brief-v3

- [x] T1 schema v3.1 — 4e41cca4. `digest_schema.py`: SeleccionEntry,
      BRIEF_CATEGORIES, brief_shape_errors cableado a validate_digest;
      tolerante (ausencia ok, malformado error). Tests
      test_digest_schema.py. Check: 33 passed.
- [x] T2 builder facts — b99eeeba. brief_delta (matching event_id/titulo
      normalizado vs día hábil previo), brief_fechas (caducada/próxima via
      parse_spanish_date), build_tarjetas, build_campo (published+review,
      window created_at), tone_label; integrado a build_daily_summary.
      Check: 40 passed.
- [x] T3 prompt v3.1 — a9cbd874. SYSTEM_PROMPT selección {index,categoria,
      razon} + prosa chica; heurístico _heuristic_brief_sections + headline
      por impacto; render BRIEF/CAMPO en plain_text; golden del esqueleto.
      Check: mezcla 46+33, verdes.
- [x] T4 compat — 5919587f. Rows v2 validan/renderizan sin keys nuevas;
      regen fallida preserva hecho/por_que vía herencia de prosa
      (tarjeta = proyección de noticias[].summary/why_it_matters);
      revisions append intacto. Check: 49 passed.
- [x] T5 verificación e2e — regen real 24-oct (stack GLM local, mode llm,
      ~21s << TIMEOUT 60, validate sin errores): /tmp/digest-2026-10-24-v3.json.
      NOTA: cobertura 43 / 33 noticias-tarjetas vs 29/9 del ejemplo — la
      diferencia es de datos/clusterización actual, no del pipeline v3.
      Campo: 1 publicada en window (los estados cambiaron desde el ejemplo).

Verificación de cierre: suite completa backend/tests = 519 passed (~21s,
dos corridas); spot check parent 25/oct: 50 passed en las 2 suites
núcleo (venv en raíz del repo, no backend/.venv).

## Tasks PR2 (frontend)

- [x] T6 dashboard — 920fa81a. Brief destacado arriba + tarjetas Evidencia +
      sección Campo con estados; container/presentacional (lógica pura en
      digest-v3.ts); smoke SSR v3 24-oct + v2 20-oct. Verificación original
      25/oct: svelte-check 0/0, 156 vitest, build OK. Cierre de doc 16/nov:
      commit ancestro de HEAD, focused vitest 21/21. Evolución posterior
      deliberada, no pérdida: F4 (75feed81) mueve Campo a superficie propia
      /campo; Brief/Evidencia siguen en DigestV3.svelte (documentado en el
      propio componente); F5-F7 posteriores sobre los mismos archivos.

## T7 calidad de cards (25/oct, post-review de Julio) — COMPLETO

- [x] Limpieza chrome FB — 619299f0. `strip_fb_chrome` idempotente en
      ingest (`to_raw_mentions`) y lectura (`build_digest_facts`): titles
      sin 'Compartido con/reacciones/Me gusta'. Check: 65 passed en las
      3 suites (summaries+schema+facebook_public).
- [x] Piso tarjetas cosméticas — fdc28581. `is_cosmetic_story` filtrada
      ANTES de prompt/brief (invariante noticias↔tarjetas intacto); la
      mención queda en cobertura y log de redes. Regen 24-oct: 33→32
      tarjetas, card de portada fuera, 0 chrome en page (spot check
      parent: 65 passed + grep SSR).
- Suite completa: 526 passed. Snapshot pre-T7 en
  backups/daily-2026-10-24-pre-t7.json (sin commit).

## T8 calidad de página (25/oct, spec aprobado con ejemplo) — COMPLETO

- [x] A merge editorial — 9ab24774. Historias gemelas fundadas en capa
      digest (umbral calibrado 0.22→0.2 contra la regen real). 24-oct:
      consulta/pensiones en 1 tarjeta con 11 fuentes; 32→12 tarjetas.
- [x] B orden por impacto — ec555227. Primeras 3 = categoría decisión
      (2 del modelo + 1 piso aditivo builder); indices del brief
      remapeados; cola fundida en tarjeta 'También hoy' (solo si total>9).
- [x] C títulos sobrios — 968c9f86. 0 emojis/hashtags/urls/@ en título
      presentacional; crudo preservado en fuentes.
- [x] D brief denso — c0ada9e3. Delta tope 5 en prosa; mínimo 3
      decisiones (piso aditivo, nunca recortar al modelo); fechas desde
      tabla agenda_items: 9 entradas con el 2026-10-28 (proxima, 4 días).
- Regen final: 12 tarjetas, delta 5, validate [] sin errores. Suite:
  546 passed (~20s). Snapshots pre-regen en backups/ (sin commit).
- Spot check parent: 73 passed core + SSR 'También hoy' presente,
  tailnet 200. Nota ops: el dev server del worktree UI hay que
  relevarlo si muere (proc background, no persiste al reiniciar).

## Transversales (fuera de los PR)

- [ ] P1 diagnóstico Instagram count 0 (ingestion o real). No bloquea.
- [ ] P2 routing por roles (`ai_roles` primary+fallback por rol, health-check
      con alarma al degradar) — feature doc propio al cerrar PR1.
- [ ] P3 eval dual del rol analysis (Spark vs DeepSeek) sobre el gate T6.

## Verificación

- Por task: `cd backend && pytest tests/test_summaries.py tests/test_digest_schema.py -q`;
  suite completa al cerrar PR1. Gate T5: regeneración 24-oct vs ejemplo.
- Convenciones y quirks del repo: skill `media-monitor-dev`
  (`~/.hermes/skills/software-development/media-monitor-dev/SKILL.md`).

## Notas

- Ejemplo aprobado 25/oct con datos reales 24/oct (brief + 9 tarjetas; campo
  con solo 2 reportes con señal, resto pruebas de pipeline).
- Historial: v3 (LLM genera todo) → v3.1 (esqueleto + selección) tras pedido de
  calidad agnóstica; aclaración de Julio: agnóstico = portar calidad
  (DeepSeek/Spark), NO bajar el piso. Mejor resultado al menor precio.
- main va ahead 2 sin push (estado 25/oct, pre-existing, no tocar).
