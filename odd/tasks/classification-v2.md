# Feature: classification-v2 (taxonomía por naturaleza de la nota)

Estado: PROPUESTA — pendiente de aprobación del usuario. No implementar sin OK.

## Diagnóstico (datos reales, 372 menciones client 1, oct 2026)

Taxonomía actual v1 (`topic` multi-label: sports/academic/culture/health/economy):

| label | menciones | observación |
|-------|-----------|-------------|
| academic | 206 | cajón de sastre: absorbe infraestructura, informes, eventos |
| economy | 88 | mezcla presupuesto institucional con notas de economía general |
| culture | 66 | razonable |
| sports | 7 | casi vacía |
| health | 5 | casi vacía |

Los temas dominantes del corpus NO tienen etiqueta: obra
infraestructura (inaugura×38, edificio×28, mural×14, campus regional×15),
gobierno universitario (informe de labores×35, rectora como actora×73,
consejo/nombramientos/toma de protesta), y vida estudiantil
(becas, movilidad, logros, protestas).

## Propuesta: 8 labels espejo del corpus

| label | definición | ejemplos del corpus |
|-------|------------|---------------------|
| `academia` | investigación, congresos, publicaciones, patentes, cuerpo académico | congreso ciencias administrativas, MentalRisk, suelos |
| `infraestructura` | obras, edificios, campus, remodelaciones, regionales | bachillerato Zacapoaxtla, CU2, mural Mixteca, CCU |
| `institucional` | gobernanza y gestión: informes, nombramientos, consejo, aniversarios, trámites/docs, jubilados | Primer Informe, toma de protesta, devolución de documentos |
| `estudiantes` | vida estudiantil: becas, movilidad, admisión, logros y protestas estudiantiles | intercambio 2027, marcha desde BUAP, 130 mil matriculados |
| `cultura` | eventos culturales y deportivos de la institución (fusiona sports; el deporte BUAP es cultural-deportivo) | calaveras CCU, sótano siniestro, ópera |
| `finanzas` | presupuesto, inversión, convenios económicos, aportaciones | Armenta equipara presupuesto 2030, 160 mdp |
| `gobierno` | relación con gobierno estatal/municipal/federal (no interna) | respaldo de Armenta, demanda ante Infonavit |
| `salud` | medicina, clínicas, investigación en salud, pandemia | VIH BUAP, dispositivo cardiovascular |

Cambios vs v1: `sports` se fusiona a `cultura` (7 datos no justifican label),
`economy` se divide en `finanzas` (institucional) vs `gobierno`, y entran
`infraestructura`/`institucional`/`estudiantes` que hoy flotan sin etiqueta.

## Implementación (v2 final: enrichment-driven)

Decisión de diseño tras medir: el choice head local (laya) se queda en
~0.46 de accuracy con 9 clases (2 iteraciones de prompt no lo mueven);
el enrichment LLM (GLM, misma llamada, costo 0) llega a **0.85**. La
clasificación canónica emite pues el ENRIQUECIMIENTO:

1. `EnrichmentResult.topic` (enum cerrado de 8, inválido => None) con reglas
   de naturaleza-del-hecho en `SYSTEM_PROMPT`; el choice head v2 queda como
   fallback para rows sin enrichment y se conserva en `topics.py`.
2. Pipeline: el upsert canonical corre DESPUÉS de los classifiers del
   registry (mismo scoping delete+insert) — el veredicto enrichment siempre
   gana. Backfill ídem.
3. Frontend: mapas `topicLabel`/`topicBadgeClass` con los 8 keys + legado
   v1 para rows viejas.
4. Gold: 48 notas con context (título + 220 chars) en
   `backend/eval_topics_gold_es.jsonl`; eval `backend/scripts/eval_topics.py`
   (head) y reproducción del path enrichment. Gate por label: todos >= 0.75,
   global 0.85; `government` n=2 ( borderline Armenta => institutional,
   defendible).

## Re-clasificación

`backend/scripts/backfill_enrichment.py --force` re-enriquece y ahora
escribe el topic canónico (además de sentimiento canónico). Los rows v1
`topic` se reemplazan por upsert; `topics` free-form del enrichment se
mantiente tal cual.

## Riesgos

- `academic` pierde volumen a favor de las nuevas labels: esperado, es el punto.
- Multi-label ambigüedad infraestructura↔institucional (inauguración presidida
  por rectora): regla de desempate en el prompt — la naturaleza del hecho manda
  (obra → infraestructura), el protagonista no.
- Costo: 1 predict por mention, mismo techo que v1.
