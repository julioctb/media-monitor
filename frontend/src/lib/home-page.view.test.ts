// @vitest-environment jsdom
import { mount, tick, unmount } from "svelte";
import { afterEach, describe, expect, it } from "vitest";

import type {
	DailySummary,
	DailySummaryContent,
	Keyword,
	PersonSummary,
} from "$lib/api";

import type { PageProps } from "../routes/$types";

import HomePage from "../routes/+page.svelte";
import { createEvidenceContext } from "$lib/digest-evidence";

/**
 * Home page view (daily structure v3): a day without a generated digest must
 * keep the mockup's daily anatomy (synthesis, date control, coverage) under
 * placeholder states instead of collapsing to a single empty legend.
 */

const mounted: Array<Record<string, unknown>> = [];

type HomeData = PageProps["data"];

function renderPage(data: HomeData): {
  text: () => string;
  container: HTMLElement;
} {
  const target = document.createElement("div");
  document.body.appendChild(target);
  const instance = mount(HomePage, {
    target,
    props: { params: {}, data, form: null },
  });
  mounted.push(instance as unknown as Record<string, unknown>);
  // Markup wraps lines: collapse whitespace so copy asserts survive reflows.
  return {
    text: () => (target.textContent ?? "").replace(/\s+/g, " "),
    container: target,
  };
}

function emptyDayData(): HomeData {
  return {
    day: "2026-10-23",
    before: null,
    summary: null,
    latest_updated_at: "2026-10-22T21:30:00Z",
    days: [],
    olderBefore: null,
    tones: null,
    keywordCounts: [],
    negativeEvents: [],
    liveCoverage: null,
    persons: [],
    keywords: [],
    digestHours: [21],
    sourcesCount: 3,
    socialLabels: {},
  };
}

function summaryFixture(): DailySummary {
  return {
    id: 1,
    client_id: 1,
    summary_date: "2026-10-23",
    content: {
      schema: 2,
      coverage: { total: 0 },
      noticias: [],
      plain_text: "texto plano",
    },
    narrative: "Narrativa editorial del día.",
    mode: "llm",
    created_at: "2026-10-23T21:00:00Z",
    updated_at: "2026-10-23T21:00:00Z",
  };
}

afterEach(() => {
  while (mounted.length) void unmount(mounted.pop() as never);
});

it('shows new indicators in the existing home card and detail surfaces', async () => {
  const summary = summaryFixture();
  const metric = { media_diversity: { identified_outlet_count: 0 }, veracity: 'not_evaluated' };
  summary.content = { indicators_version: 1,
    noticias: [{ title: 'Historia', event_id: 7, summary: 'Reseña íntegra.', sources: [], ...metric }],
    tarjetas: [{ titulo: 'Historia', hecho: 'Reseña íntegra.', ...metric }] } as never;
  const { container, text } = renderPage({ ...emptyDayData(), summary }); await tick();
  expect(container.querySelector('.digest-tarjeta')?.textContent).toContain('Diversidad de medios: 0 medios identificados');
  expect(container.querySelector('.daily-detail-entry')?.textContent).toContain('Veracidad no evaluada');
  expect(text()).not.toContain('Confianza');
});

const PLACEHOLDER = "En espera de generar el resumen del día";

it("keeps the daily structure with placeholders when the digest is missing", () => {
  const { text } = renderPage(emptyDayData());

  // Synthesis wait state + cutoff copy under the mockup headings.
  expect(text()).toContain("Resumen diario / BUAP");
  expect(text()).toContain("Síntesis del día");
  expect(text()).toContain(PLACEHOLDER);
  expect(text()).toContain("En espera del primer corte del día");

  // The daily skeleton stays in place: agenda + coverage method panels.
  expect(text()).toContain("Agenda y plazos");
  expect(text()).toContain("Cobertura y método");

  // Old single-legend empty state is gone.
  expect(text()).not.toContain("Todavía no se genera el resumen del día");
});

it("renders the narrative and hides the placeholder once the digest exists", () => {
  const data = { ...emptyDayData(), summary: summaryFixture() };
  const { text } = renderPage(data);

  expect(text()).toContain("Narrativa editorial del día.");
  expect(text()).not.toContain(PLACEHOLDER);
  expect(text()).toContain("Actualizado a las");
});

it("joins the active keywords to the eyebrow after Resumen diario", () => {
  const data = {
    ...emptyDayData(),
    summary: summaryFixture(),
    keywords: [
      { id: 7, text: "BUAP", is_active: true },
      { id: 9, text: "Lilia Cedillo", is_active: true },
    ],
  } as never;
  const { container } = renderPage(data);

  const heading = container.querySelector(".daily-synthesis-heading")?.textContent ?? "";
  expect(heading).toContain("Resumen diario / BUAP · Lilia Cedillo");
});

it("falls back to Resumen diario / BUAP without active keywords", () => {
  const { text } = renderPage({ ...emptyDayData(), summary: summaryFixture() });

  expect(text()).toContain("Resumen diario / BUAP");
});

it("renders the v3 brief as executive panels without the plain narrative block", () => {
  const v3Summary: DailySummary = {
    ...summaryFixture(),
    content: {
      ...summaryFixture().content,
      brief: {
        headline: "Narrativa editorial del día.",
        delta: ["Nueva historia: A"],
        decisiones: [{ index: 0, categoria: "decision", razon: "Impacto" }],
        ruido: [],
        a_favor: [],
        fechas: [],
      },
      tarjetas: [
        {
          titulo: "A",
          hecho: "Hecho uno",
          fuentes: ["news_rss"],
          repeat: false,
        },
      ],
      campo: [{ titulo: "Reporte", estado: "publicada" }],
    } as never,
  };
  const { container, text } = renderPage({ ...emptyDayData(), summary: v3Summary });
  const copy = text();

  // The brief feeds the executive panels; the promoted prose leads the synthesis.
  expect(copy).toContain("Qué requiere atención");
  expect(copy).toContain("Qué cambió");
  // Delta lines resolve their story against the tarjeta pool (title, not raw line).
  expect(container.querySelector('.daily-changes')?.querySelectorAll('li').length).toBe(1);
  expect(copy).toContain("Narrativa editorial del día.");
  expect(copy).toContain("Hecho uno");
  // F4: the campo key may travel, but the digest no longer renders it.
  expect(copy).not.toContain("reportes en la ventana");
});

it("keeps the legacy narrative on v2 rows without brief keys", () => {
  const { text } = renderPage({ ...emptyDayData(), summary: summaryFixture() });

  expect(text()).toContain("Síntesis del día");
  // No brief keys: no fabricated executive panels.
  expect(text()).not.toContain("Qué requiere atención");
  expect(text()).not.toContain("Qué cambió");
});

it('does not mark the waiting placeholder as unbacked', async () => {
  const { text } = renderPage(emptyDayData()); await tick();
  expect(text()).toContain(PLACEHOLDER);
  expect(text()).not.toContain('No respaldado');
});
it('marks a historical narrative without removing any prose', async () => {
  const { container } = renderPage({ ...emptyDayData(), summary: summaryFixture() }); await tick();
  expect(container.querySelector('.daily-synthesis-lead')?.textContent).toContain('Narrativa editorial del día.');
  expect(container.querySelector('.daily-synthesis')?.textContent).toContain('No respaldado');
});
it('binds the leading prose to the actual raw narrative, not a stale headline copy', async () => {
  const summary = summaryFixture();
  summary.content.evidence = { version: 1, sources: [{ index: 0, mention_id: 1,
    source: 'news_rss', url: 'https://medio.example/1', outlet: 'medio.example', author: null,
    title: 'Publicación registrada', published_at: null, summary: null, excerpt: 'Material' }] } as never;
  const fingerprint = (await createEvidenceContext(summary.content))!.fingerprint;
  summary.content.brief = { headline: 'Copia vieja del titular' } as never;
  summary.content.provenance = { headline: { text: summary.narrative, source_refs: [0], state: 'linked', origin: 'model_output', catalogue_fingerprint: fingerprint } } as never;
  const { container, text } = renderPage({ ...emptyDayData(), summary });
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  expect(container.querySelector('.daily-synthesis-lead')?.textContent).toBe(summary.narrative);
  expect(text()).not.toContain('Copia vieja del titular');
  expect(container.querySelector('.daily-synthesis details summary')?.textContent).toBe('Fuentes vinculadas');
});

it('retains a valid legacy brief headline when the actual narrative is empty', async () => {
  const summary = summaryFixture(); summary.narrative = '';
  summary.content.brief = { headline: 'Titular histórico íntegro' } as never;
  const { container } = renderPage({ ...emptyDayData(), summary }); await tick();
  expect(container.querySelector('.daily-synthesis-lead')?.textContent).toBe('Titular histórico íntegro');
  expect(container.querySelector('.daily-synthesis')?.textContent).toContain('No respaldado');
});

/* ------------------------------------------------------------------ */
/* Mockup daily-view anatomy parity (structure, not just skin).        */
/* ------------------------------------------------------------------ */

/** digest-brief-v3 content with action/condition picks (digest-v3 shape). */
function v3Content(): DailySummaryContent {
  return {
    schema: 2,
    coverage: { total: 2 },
    noticias: [
      {
        event_id: 7,
        title: 'Nota v2',
        summary: 'Resumen v2',
        sources: [{ source: 'news_rss', url: 'https://a/1' }],
      },
    ],
    plain_text: 'texto',
    brief: {
      headline: 'Titular del día',
      delta: ['Nueva historia: A', 'B: el tono pasa de positivo a negativo'],
      decisiones: [
        {
          index: 0,
          categoria: 'decision',
          razon: 'Impacto presupuestal',
          accion_sugerida: 'Guardar minuta y dar seguimiento',
          condicion: 'Si el colegiado aprueba el punto',
        },
      ],
      riesgos: [
        {
          index: 0,
          categoria: 'riesgo',
          razon: 'tono negativo dominante',
          afectacion: { quien: ['Rectora Cedillo'] },
        },
      ],
      ruido: [{ index: 1, categoria: 'ruido' }],
      a_favor: [],
      vigilancia: [
        {
          persona: 'Lilia Cedillo',
          nota: 'Critican la gestión de becas',
          fecha: '2026-10-09T13:00:00-06:00',
          afectacion: { quien: ['Lilia Cedillo'] },
        },
      ],
      descarte: { cosmeticas: 2, fundadas: 1 },
      fechas: [
        { title: 'Cierre de registro', when: '27 oct.', estado: 'proxima', fecha: '2026-10-27' },
        { title: 'Vencido', when: '1 oct.', estado: 'caducada', fecha: '2026-10-01' },
        { title: 'Raro', when: 'algún día', estado: 'otro', fecha: null },
      ],
    },
    tarjetas: [
      {
        titulo: 'A',
        hecho: 'Hecho uno',
        por_que: 'Porque uno',
        fuentes: ['news_rss', 'news_rss', 'x_twitter'],
        tono: 'negativo',
        repeat: true,
        angulo_nuevo: 'Nuevo ángulo',
      },
    ],
    campo: [],
  } as unknown as DailySummaryContent;
}

function populatedDayData(): HomeData {
  const summary: DailySummary = {
    id: 1,
    client_id: 1,
    summary_date: '2026-10-28',
    content: v3Content(),
    narrative: 'Síntesis narrativa del día.',
    mode: 'llm',
    created_at: '2026-10-28T07:10:00-06:00',
    updated_at: '2026-10-28T13:10:00-06:00',
  };
  const keyword: Keyword = {
    id: 1,
    text: 'BUAP',
    language: 'es' as Keyword['language'],
    is_active: true,
    created_at: '2026-10-01T00:00:00-06:00',
  };
  const person: PersonSummary = {
    id: 4,
    name: 'Lilia Cedillo',
    name_key: 'lilia-cedillo',
    role: 'Rectora',
    org: 'BUAP',
    aliases: [],
    first_seen_at: '2026-10-01T08:00:00-06:00',
    last_seen_at: '2026-10-28T09:00:00-06:00',
    mention_count: 9,
  };
  return {
    day: '2026-10-28',
    before: null,
    summary,
    latest_updated_at: '2026-10-27T22:40:00-06:00',
    days: [{ summary_date: '2026-10-28' }, { summary_date: '2026-10-27' }],
    olderBefore: '2026-09-01',
    tones: null,
    keywordCounts: [{ id: 1, text: 'BUAP', count: 4 }],
    negativeEvents: [],
    liveCoverage: { total: 8, byTopic: { politica: 6, finanzas: 2 }, events: 2 },
    persons: [person],
    keywords: [keyword],
    digestHours: [7, 13, 19],
    sourcesCount: 12,
    socialLabels: {},
  } as unknown as HomeData;
}

describe('home daily structure (v3 mockup)', () => {
  it('renders the daily anatomy with a populated summary', () => {
    const { container, text } = renderPage(populatedDayData());

    expect(container.querySelector('.daily-page')).toBeTruthy();
    expect(text()).toContain('Síntesis del día');
    expect(text()).toContain('Síntesis narrativa del día.');
    expect(text()).toContain('Resumen diario / BUAP');

    // Briefing calendar: local weekday/day/month, ISO datetime attr.
    const calendar = container.querySelector('.briefing-calendar');
    expect(calendar?.getAttribute('datetime')).toBe('2026-10-28');
    expect(calendar?.querySelector('.briefing-day')?.textContent?.trim()).toBe('28');
    expect(calendar?.querySelector('.briefing-weekday')?.textContent?.trim()?.length ?? 0).toBeGreaterThan(2);

    // Executive priorities: numbered cards with category badge.
    const priorities = [...container.querySelectorAll('.executive-priority')];
    expect(priorities.length).toBeGreaterThanOrEqual(3);
    expect(priorities[0].querySelector('.daily-number')?.textContent?.trim()).toBe('01');
    expect(priorities[0].querySelector('.source-badge')?.textContent?.trim()?.length ?? 0).toBeGreaterThan(3);

    // Parallel actions panel only lists picks with an action/condition.
    const actions = container.querySelector('.executive-actions');
    expect(actions?.textContent).toContain('Guardar minuta y dar seguimiento');
    expect(actions?.textContent).toContain('Si el colegiado aprueba el punto');

    // Delta (Qué cambió) and vigilancia map their brief rows.
    expect(container.querySelector('.daily-changes')?.querySelectorAll('li').length).toBe(2);
    expect(container.querySelector('[aria-labelledby="daily-vigilancia-heading"]')?.textContent)
      .toContain('Lilia Cedillo');

    // Actors: the name is the link to the person page.
    expect(container.querySelector('[aria-labelledby="daily-actors-heading"] a')?.getAttribute('href'))
      .toBe('/persons/4');

    // Agenda deadlines keep their estado chip; coverage counts the day.
    expect(container.querySelectorAll('.daily-deadline').length).toBe(3);
    const coverageSummary =
      (container.querySelector('.executive-coverage summary')?.textContent ?? '').replace(/\s+/g, ' ');
    expect(coverageSummary).toContain('8 notas registradas');
  });

  it('offers archive days and the older-month link', () => {
    const { container } = renderPage(populatedDayData());

    const select = container.querySelector('#day-jump') as HTMLSelectElement | null;
    expect(select?.querySelectorAll('option').length).toBe(2);
    expect(select?.value).toBe('2026-10-28');

    const older = container.querySelector('.briefing-date-picker a.text-link');
    expect(older?.getAttribute('href')).toContain('before=2026-09-01');
    expect(older?.textContent).toContain('ver mes anterior');
  });

  it('degrades to waiting copy with an empty day, keeping the shell', () => {
    const { container, text } = renderPage(emptyDayData());

    expect(container.querySelector('.daily-page')).toBeTruthy();
    expect(text()).toContain(PLACEHOLDER);
    expect(text()).toContain('No se identifican personas en los registros de esta fecha.');

    // No fabricated panels when the day has no brief.
    expect(container.querySelector('.executive-priorities')).toBeNull();
    expect(container.querySelector('.executive-actions')).toBeNull();
    expect(container.querySelector('.daily-changes')).toBeNull();
    const coverageSummary =
      (container.querySelector('.executive-coverage summary')?.textContent ?? '').replace(/\s+/g, ' ');
    expect(coverageSummary).toContain('— notas registradas');
  });
});
