# Feature: monitoreo de columnas y columnistas (BUAP)

## Objetivo
Que las columnas de opinión que mencionan BUAP entren al feed con su autor
identificado, para seguir a los columnistas.

## Problema
- Solo 31/499 menciones tienen `author`: el dato existe en el modelo y el
  feed (columna UI pendible) pero nada lo captura.
- No hay scraping de secciones de opinión (0 URLs /opinion).
- RSS: jornada e hipocrita traen author en el feed; hoy se descarta.

## Tareas
- [x] T1 feeds.py: author desde entry.author / author_detail; test RED→GREEN
- [x] T2 article_fetch: ArticleContent(text, author) con extracción por meta
      tags; pipeline desembolsa author (duck-typing para compat); test
- [x] T3 scrapers: e_consulta += list_url /opinion (parser genérico compatible)
- [x] T4 MentionCard: "Por {author}" en metadata; test
- [x] T5 deploy + verificación en vivo

## Fuera de alcance (fase 2)
- laredaccion: sin sección opinión visible. Jornada /opinion: 403 a bots, el
  feed principal ya cubre sus columnas con autor.
- Ranking de columnistas (vista propia): requiere volumen de datos con author;
  candidatos: /persons extendida o filtro por `author IS NOT NULL`.

## Route / verificación
- Inline (fix acotado, archivos conocidos, suite cubre). Writer self-check medium.
- `.venv/bin/python -m pytest backend/tests -q`; frontend vitest + check.
- Work-unit commits en feat/scraper-ingest.

## Estado
- T1-T5 OK. Commit author pipeline: 1864c1c (feeds dc:creator + meta tags, duck-typing compat).
- Pendiente usuario: SMTP para que las alertas lleguen; decidir vista de
  ranking de columnistas cuando haya volumen.
