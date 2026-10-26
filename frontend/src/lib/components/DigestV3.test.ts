// @vitest-environment jsdom
import { mount, tick, unmount } from "svelte";
import { afterEach, expect, it } from "vitest";

import type { DailySummaryContent } from "$lib/api";

import DigestV3 from "./DigestV3.svelte";
import { createEvidenceContext } from "$lib/digest-evidence";

/**
 * Container behavior: v3 rows render brief + evidencia + campo; legacy v2
 * rows render NOTHING (the home keeps its layout, no ghost sections).
 */

const mounted: Array<Record<string, unknown>> = [];

function render(content: unknown): { text: () => string; html: () => string; target: HTMLElement } {
  const target = document.createElement("div");
  document.body.appendChild(target);
  const instance = mount(DigestV3, {
    target,
    props: { content: content as never },
  });
  mounted.push(instance as unknown as Record<string, unknown>);
  return {
    text: () => (target.textContent ?? "").replace(/\s+/g, " "),
    html: () => target.innerHTML,
    target,
  };
}

afterEach(() => {
  while (mounted.length) void unmount(mounted.pop() as never);
});

function v3Content(): Record<string, unknown> {
  return {
    schema: 2,
    noticias: [],
    brief: {
      headline: "Titular del día",
      delta: ["Nueva historia: A", "Consulta pensionaria: el tono pasa de positivo a negativo"],
      decisiones: [
        { index: 0, categoria: "decision", razon: "Impacto presupuestal" },
      ],
      riesgos: [
        {
          index: 1,
          categoria: "riesgo",
          razon: "tono negativo dominante",
          afectacion: { quien: ["Rectora Cedillo"], trayectoria: "el tono pasa de mixto a negativo" },
        },
      ],
      ruido: [],
      a_favor: [],
      vigilancia: [
        {
          persona: "Lilia Cedillo",
          nota: "Critican la gestión de becas",
          fecha: "2026-10-09T13:00:00-06:00",
          afectacion: { quien: ["Lilia Cedillo"] },
        },
      ],
      fechas: [
        {
          title: "Cierre",
          when: "27 oct.",
          estado: "proxima",
          fecha: "2026-10-27",
        },
      ],
      descarte: { cosmeticas: 2, fundadas: 1 },
    },
    tarjetas: [
      {
        titulo: "A",
        hecho: "Hecho uno",
        por_que: "Porque importa",
        fuentes: ["news_rss"],
        tono: "negativo",
        repeat: true,
      },
      { titulo: "B", hecho: "Hecho dos", fuentes: [], repeat: false },
    ],
    campo: [
      { titulo: "Reporte", contenido: "Texto", estado: "publicada" },
      { titulo: "Pendiente", estado: "en revisión" },
    ],
  };
}

it("renders nothing for legacy v2 content", () => {
  const view = render({ schema: 2, noticias: [], plain_text: "x" });
  expect(view.text()).toBe("");
});

it("renders brief and evidencia; campo stays out of the digest (F4)", () => {
  const { text } = render(v3Content());
  const copy = text();

  // Brief hero.
  expect(copy).toContain("Brief del día");
  expect(copy).toContain("Titular del día");
  expect(copy).toContain("Qué cambió");
  // Delta tipado (25/oct): sin prefijo «Nueva historia» repetido; el giro
  // de tono viaja como nota en peso normal tras el título.
  expect(copy).not.toContain("Nueva historia");
  expect(copy).toContain("Consulta pensionaria — el tono pasa de positivo a negativo");
  // F5: el riesgo encabeza los picks del brief, con su afectación.
  expect(copy).toContain("Riesgo");
  expect(copy).toContain("B — tono negativo dominante");
  expect(copy).toContain("Quién: Rectora Cedillo");
  expect(copy).toContain("Trayectoria: el tono pasa de mixto a negativo");
  // F7: la línea de vigilancia con su fecha y afectación.
  expect(copy).toContain("Vigilancia");
  expect(copy).toContain("Lilia Cedillo");
  expect(copy).toContain("Critican la gestión de becas");
  expect(copy).toContain("Quién: Lilia Cedillo");
  expect(copy).toContain("Decisión / atención");
  expect(copy).toContain("A — Impacto presupuestal");
  expect(copy).toContain("Fechas que obligan");
  expect(copy).toContain("Próxima Cierre (27 oct.)");
  // F3: visible discard line.
  expect(copy).toContain(
    "Descartado: 2 actualizaciones cosméticas, 1 historia fundida",
  );

  // Evidencia cards: hecho, por qué, fuente y badges.
  expect(copy).toContain("Evidencia del día");
  expect(copy).toContain("Hecho uno");
  expect(copy).toContain("Por qué — Porque importa");
  expect(copy).toContain("Fuente: News RSS");
  expect(copy).toContain("Reiteración");
  expect(copy).toContain("negativo");

  // F4: the campo section no longer renders in the digest, key or not.
  expect(copy).not.toContain("reportes en la ventana");
  expect(copy).not.toContain("Campo");
});

it("hides absent pieces: no por_que, no ghost sections", () => {
  const content = v3Content();
  const tarjetas = content.tarjetas as Record<string, unknown>[];
  tarjetas[1].hecho = null;
  delete tarjetas[0].por_que;
  delete content.campo;
  delete (content.brief as Record<string, unknown>).descarte;
  const { text } = render(content);

  expect(text()).not.toContain("Por qué");
  expect(text()).not.toContain("Hecho dos");
  expect(text()).not.toContain("Descartado");
  expect(text()).not.toContain("reportes en la ventana");
  expect(text()).toContain("Hecho uno");
});


it("retains legacy analytical prose with visible unbacked markers", async () => {
  const { text, html } = render(v3Content());
  await tick();
  expect(text()).toContain("Hecho uno");
  expect(text()).toContain("Impacto presupuestal");
  expect(html()).toContain("No respaldado");
  expect(html()).not.toContain("Fuentes vinculadas");
});

async function linkedContent() {
  const sources = [0, 1, 2].map(index => ({ index, mention_id: 10 + index,
    source: 'news_rss', url: `https://medio.example/${index}`, outlet: 'medio.example',
    author: null, title: `Publicación ${index}`, published_at: null, summary: null, excerpt: `Material ${index}` }));
  const content: Record<string, unknown> = { ...v3Content(), evidence: { version: 1, sources } };
  const fingerprint = (await createEvidenceContext(content))!.fingerprint;
  const binding = (text: string, source: number) => ({ text, source_refs: [source], state: 'linked', origin: 'model_output', catalogue_fingerprint: fingerprint });
  const tarjetas = content.tarjetas as Record<string, unknown>[];
  tarjetas[0] = { titulo: 'A', hecho: ' Hecho https://enlace.example/ crudo ', por_que: 'Porque importa', angulo_nuevo: 'Lectura nueva', fuentes: [], source_refs: [0], provenance: {
    hecho: binding(' Hecho https://enlace.example/ crudo ', 0), por_que: binding('Porque importa', 0), angulo_nuevo: binding('Lectura nueva', 0)
  } };
  const brief = content.brief as Record<string, unknown>;
  brief.decisiones = [{ index: 0, razon: 'Razón vinculada', provenance: { razon: binding('Razón vinculada', 0) } }];
  return { content, binding };
}

it('carries exact raw card and selection bindings through the existing view', async () => {
  const { content } = await linkedContent();
  const { target, text } = render(content);
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  const first = target.querySelector('.digest-tarjeta')!;
  expect(first.querySelectorAll('details summary')).toHaveLength(3);
  expect(first.textContent).toContain('Hecho crudo');
  expect(text()).toContain('Razón vinculada');
  const choice = [...target.querySelectorAll('.digest-brief-block')].find(block => block.textContent?.includes('Decisión / atención'))!;
  expect(choice.querySelector('details summary')?.textContent).toBe('Fuentes vinculadas');
  expect([...first.querySelectorAll('a')].every(link => link.getAttribute('href') === 'https://medio.example/0')).toBe(true);
  expect(first.textContent).not.toContain('Material 2');
});

it('renders every compiled bullet with its own scope after card reordering', async () => {
  const { content, binding } = await linkedContent();
  const compiled = { titulo: 'También hoy', notas: ['Nota B', '', 'Nota A'], source_refs: [0, 1],
    notas_refs: [{ source_refs: [1] }, {}, { source_refs: [0] }],
    provenance: { notas: [binding('Nota B', 1), null, binding('Nota A', 0)] }, fuentes: [] };
  content.tarjetas = [null, compiled, { titulo: 'Después', hecho: 'Texto sin respaldo' }];
  const { target, text } = render(content);
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  const bullets = [...target.querySelectorAll('.digest-tarjeta-notas > li')];
  expect(bullets).toHaveLength(2);
  expect(bullets.map(bullet => bullet.textContent?.slice(0, 6))).toEqual(['Nota B', 'Nota A']);
  expect(bullets.map(bullet => bullet.querySelector('a')?.getAttribute('href'))).toEqual(['https://medio.example/1', 'https://medio.example/0']);
  expect(text()).toContain('Texto sin respaldo');
  compiled.notas_refs[0] = { source_refs: [0] };
  const changed = render(content);
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  expect(changed.target.querySelector('.digest-tarjeta-notas > li')?.textContent).toContain('No respaldado');
  expect(changed.target.querySelector('.digest-tarjeta-notas > li')?.querySelector('a')).toBeNull();
});

it('retains all displayed prose while stale, foreign and changed raw bindings become unbacked', async () => {
  const { content } = await linkedContent();
  const cards = content.tarjetas as Record<string, unknown>[];
  cards[0].hecho = 'Otro hecho sin referencia válida';
  (cards[0].provenance as Record<string, { source_refs: number[] }>).por_que.source_refs = [1];
  const { target, text } = render(content);
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  expect(text()).toContain('Otro hecho sin referencia válida');
  expect(text()).toContain('Porque importa');
  const first = target.querySelector('.digest-tarjeta')!;
  expect(first.querySelectorAll('span.digest-provenance')).toHaveLength(2);
  expect(first.querySelectorAll('details')).toHaveLength(1);
  const evidence = content.evidence as { catalogue_fingerprint?: string; sources: { excerpt: string }[] };
  evidence.catalogue_fingerprint = (await createEvidenceContext(content))!.fingerprint;
  evidence.sources[0].excerpt = 'Material modificado';
  const changed = render(content);
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  expect(changed.target.querySelector('.digest-tarjeta')?.querySelectorAll('details')).toHaveLength(0);
  expect(changed.text()).toContain('Lectura nueva');
});

it('keeps new analysis notes separately linked to their original raw text', async () => {
  const { content, binding } = await linkedContent();
  content.indicators_version = 1;
  const card = (content.tarjetas as Record<string, unknown>[])[0];
  Object.assign(card, { media_diversity: { identified_outlet_count: 1 }, veracity: 'not_evaluated', confidence_note: 'Nota https://enlace.example/ cruda' });
  (card.provenance as Record<string, unknown>).confidence_note = binding(card.confidence_note as string, 0);
  const { target } = render(content);
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  const first = target.querySelector('.digest-tarjeta')!;
  expect(first.textContent).toContain('Nota del análisis: Nota cruda');
  expect(first.textContent).toContain('Diversidad de medios: 1 medio identificado');
  expect(first.querySelectorAll('details summary')).toHaveLength(4);
  expect([...first.querySelectorAll('a')].every(link => link.getAttribute('href') === 'https://medio.example/0')).toBe(true);
});
