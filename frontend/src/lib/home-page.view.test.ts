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

const PLACEHOLDER = "En espera de generar el resumen del día";

it("shows the mockup empty panel when the day has no digest", () => {
  const { container, text } = renderPage(emptyDayData());

  // Mockup empty state: date control + panel.empty, no synthesis panel.
  expect(container.querySelector(".daily-page .panel.empty")).toBeTruthy();
  expect(text()).toContain("Sin información para elaborar el resumen");
  expect(text()).toContain(
    "No hay registros en esta fecha. La ausencia de datos no implica ausencia de incidentes."
  );
  expect(text()).toContain("En espera del primer corte del día");
  expect(container.querySelector(".daily-synthesis")).toBeNull();

  // Picker disabled without recorded days (mockup: «Sin fechas con registros»).
  const select = container.querySelector("#day-jump") as HTMLSelectElement | null;
  expect(select?.disabled).toBe(true);
  expect(text()).toContain("Sin fechas con registros");

  // No fabricated panels on an empty day.
  expect(container.querySelector(".executive-priorities")).toBeNull();
  expect(container.querySelector(".daily-actors")).toBeNull();
  expect(container.querySelector(".executive-coverage")).toBeNull();
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
  expect(copy).toContain("Hasta tres asuntos");
  // Delta lives INSIDE the cards as the «cambio» row — no standalone section.
  expect(copy).toContain("Cambio respecto al corte anterior");
  expect(container.querySelector(".daily-changes")).toBeNull();
  expect(copy).toContain("Narrativa editorial del día.");
  // F4: the campo key may travel, but the digest no longer renders it.
  expect(copy).not.toContain("reportes en la ventana");
  // Tarjetas/evidencia grid left home with the sweep (evidence is inline).
  expect(copy).not.toContain("Hecho uno");
  expect(copy).not.toContain("Evidencia del día");
});

it("keeps the legacy narrative on v2 rows without brief keys", () => {
  const { container, text } = renderPage({ ...emptyDayData(), summary: summaryFixture() });

  expect(text()).toContain("Síntesis del día");
  // No brief keys: no fabricated executive panels.
  expect(container.querySelector(".executive-priorities")).toBeNull();
  expect(text()).not.toContain("Qué requiere atención");
  expect(text()).not.toContain("Decisiones y acciones sugeridas");
});

it("keeps the acciones section visible without actions, per the mockup anatomy", () => {
  const noActionSummary: DailySummary = {
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
      tarjetas: [],
      campo: [],
    } as never,
  };
  const { container } = renderPage({ ...emptyDayData(), summary: noActionSummary });

  // The section is first-class mockup anatomy: present with an honest note.
  const section = container.querySelector(".executive-actions");
  expect(section).toBeTruthy();
  expect(section?.textContent).toContain("Sin acciones sugeridas en el corte de este día.");
  expect(container.querySelector(".executive-action")).toBeNull();
});

it('does not mark the empty-day panel as unbacked', async () => {
  const { text } = renderPage(emptyDayData()); await tick();
  expect(text()).toContain('Sin información para elaborar el resumen');
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
      a_favor: [{ index: 0, categoria: 'a_favor', razon: 'Postura favorable documentada' }],
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
    expect((calendar?.querySelector('.briefing-weekday')?.textContent?.trim() ?? '').length).toBeGreaterThan(2);

    // Priorities cap at three; the mockup never surfaces the rest (its
    // «otros asuntos» branch is unreachable with demo data) — nothing after.
    const priorities = [...container.querySelectorAll('.executive-priority')];
    expect(priorities.length).toBe(3);
    expect(priorities[0].querySelector('.daily-number')?.textContent?.trim()).toBe('01');
    expect((priorities[0].querySelector('.source-badge')?.textContent?.trim() ?? '').length).toBeGreaterThan(3);
    expect(container.querySelector('.executive-other')).toBeNull();

    // Card facts: mockup copy with the delta-driven cambio row.
    const firstCard = (priorities[0].textContent ?? '').replace(/\s+/g, ' ');
    expect(firstCard).toContain('Por qué importa · lectura política');
    expect(firstCard).toContain('Cambio respecto al corte anterior');

    // Actions panel: mockup anatomy with per-item plazo row.
    const actions = container.querySelector('.executive-actions');
    expect(actions?.textContent).toContain('Guardar minuta y dar seguimiento');
    expect(actions?.textContent).toContain('Plazo documentado');
    expect(actions?.textContent).toContain('No consta un plazo en los registros.');

    // Actors: static non-attribution note; the name links to the person page.
    expect(text()).toContain('Una mención no atribuye responsabilidad.');
    expect(container.querySelector('.daily-actor strong a')?.getAttribute('href')).toBe('/persons/4');
    // Missing links (mockup affordances): panel-level directory link plus a
    // per-actor explicit CTA to the ficha.
    const actorsPanel = container.querySelector('.daily-actors');
    expect(actorsPanel?.querySelector('.daily-panel-head a')?.getAttribute('href')).toBe('/persons');
    expect(actorsPanel?.querySelector('.daily-panel-head a')?.textContent).toContain('Ver directorio');
    const personLinks = [...(actorsPanel?.querySelectorAll('a[href="/persons/4"]') ?? [])];
    expect(personLinks.some((a) => a.textContent?.includes('Ver ficha y menciones'))).toBe(true);

    // Agenda: mockup daily-upcoming items with date-box and honest estado.
    const upcoming = [...container.querySelectorAll('.daily-upcoming')];
    expect(upcoming.length).toBe(3);
    const firstDateBox = upcoming[0].querySelector('.date-box');
    expect(firstDateBox?.querySelector('span')?.textContent?.trim()).toBe('OCT');
    expect(firstDateBox?.querySelector('strong')?.textContent?.trim()).toBe('27');
    expect(upcoming[0].textContent ?? '').toContain('Fecha detectada en publicación');
    expect(upcoming[0].textContent ?? '').toContain('compromiso no confirmado');

    // Coverage: mockup copy + veracity badge.
    const coverageSummary =
      (container.querySelector('.executive-coverage summary')?.textContent ?? '').replace(/\s+/g, ' ');
    expect(coverageSummary).toContain('8 publicaciones analizadas');
    expect(container.querySelector('.daily-veracity')?.textContent?.trim()).toBe('Veracidad no evaluada');

    // Surplus legacy sections are gone (v3 sweep).
    expect(container.querySelector('.daily-changes')).toBeNull();
    expect(container.querySelector('[aria-labelledby="daily-vigilancia-heading"]')).toBeNull();
    expect(container.querySelector('.digest-evidencia')).toBeNull();
    expect(text()).not.toContain('Resumen general');
  });

  it('offers archive days and the older-month link', () => {
    const { container } = renderPage(populatedDayData());

    const picker = container.querySelector('.briefing-date-picker');
    expect(picker?.querySelector('label')?.textContent).toContain('Cambiar fecha');
    const select = container.querySelector('#day-jump') as HTMLSelectElement | null;
    expect(select?.disabled).toBeFalsy();
    expect(select?.querySelectorAll('option').length).toBe(2);
    expect(select?.value).toBe('2026-10-28');

    const older = picker?.querySelector('a.text-link');
    expect(older?.getAttribute('href')).toContain('before=2026-09-01');
    expect(older?.textContent).toContain('ver mes anterior');
  });

  it('opens the evidence dialog from a priority card', async () => {
    const { container } = renderPage(populatedDayData());

    const button = container.querySelector<HTMLButtonElement>(
      '.executive-priority .executive-evidence button'
    );
    expect(button?.textContent).toContain('Ver fuentes y detalle');
    button?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 30));
    await tick();

    const dialog = container.querySelector('dialog.detail-dialog');
    expect(dialog).toBeTruthy();
    const text = (dialog?.textContent ?? '').replace(/\s+/g, ' ');
    expect(text).toContain('Materiales del corte actual · 0');
    expect(text).toContain('No hay fuentes vinculadas a esta entrada en el corte.');
    expect(text).toContain('Lectura política · interpretación');
    expect(text).toContain('No respaldada como hecho.');
    expect(text).toContain('Veracidad no evaluada');
  });

  it('empty day renders only the date control and the mockup empty panel', () => {
    const { container } = renderPage(emptyDayData());

    expect(container.querySelector('.daily-page')).toBeTruthy();
    expect(container.querySelector('.panel.empty')).toBeTruthy();
    expect(container.querySelector('.executive-actions')).toBeNull();
    expect(container.querySelector('.daily-actors')).toBeNull();
  });
});
