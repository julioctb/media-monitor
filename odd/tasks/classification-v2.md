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

## Implementación (mecanismo intacto)

1. `TOPICS` v2 en el prompt del clasificador (registry `app/classifications/`),
   mismas N preguntas binarias de un solo predict; defs + 2 ejemplos
   positivos/negativos por label, regla carve-out político viva.
2. Clasificador interno: nombre de classifier sigue siendo `topic` (upsert
   sustituye rows; sin migración). Frontend: ampliar mapas de
   `topicLabel`/`topicBadgeClass` en `format.ts` (labels ES + color por label).
3. Gold: 40 títulos del corpus etiquetados a mano (los ya listados arriba
   sirven de semilla) → precisión por label ≥ 0.8 antes de backfill.
4. Backfill: re-clasificar los 372 con `--classifications` tras calibrar;
   political se mantiene intacto (binary v1 con calibración propia).

## Riesgos

- `academic` pierde volumen a favor de las nuevas labels: esperado, es el punto.
- Multi-label ambigüedad infraestructura↔institucional (inauguración presidida
  por rectora): regla de desempate en el prompt — la naturaleza del hecho manda
  (obra → infraestructura), el protagonista no.
- Costo: 1 predict por mention, mismo techo que v1.
