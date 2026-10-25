// @vitest-environment jsdom
import { mount, unmount } from "svelte";
import { afterEach, expect, it } from "vitest";

import type { DailySummaryContent } from "$lib/api";

import DigestV3 from "./DigestV3.svelte";

/**
 * Container behavior: v3 rows render brief + evidencia + campo; legacy v2
 * rows render NOTHING (the home keeps its layout, no ghost sections).
 */

const mounted: Array<Record<string, unknown>> = [];

function render(content: unknown): { text: () => string; html: () => string } {
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
      delta: ["Nueva historia: A"],
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
  expect(copy).toContain("Nueva historia: A");
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
