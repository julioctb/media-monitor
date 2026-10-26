import { describe, expect, it } from "vitest";

import type { DailySummaryContent } from "$lib/api";

import { digestV3View, hasDigestV3 } from "./digest-v3";

/** Legacy v2 row: no brief/tarjetas/campo keys at all. */
function v2Content(): DailySummaryContent {
  return {
    schema: 2,
    coverage: { total: 2 },
    noticias: [
      {
        event_id: 7,
        title: "Nota v2",
        summary: "Resumen v2",
        sources: [{ source: "news_rss", url: "https://a/1" }],
      },
    ],
    plain_text: "texto",
  };
}

function v3Content(): DailySummaryContent {
  return {
    ...v2Content(),
    brief: {
      headline: "Titular del día",
      delta: ["Nueva historia: A", "B: el tono pasa de positivo a negativo"],
      decisiones: [{ index: 0, categoria: "decision", razon: "Impacto presupuestal" }],
      riesgos: [
        {
          index: 0,
          categoria: "riesgo",
          razon: "tono negativo dominante",
          afectacion: { quien: ["Rectora Cedillo"] },
        },
      ],
      ruido: [{ index: 1, categoria: "ruido" }],
      a_favor: [],
      vigilancia: [
        {
          persona: "Lilia Cedillo",
          nota: "Critican la gestión de becas",
          fecha: "2026-10-09T13:00:00-06:00",
          afectacion: { quien: ["Lilia Cedillo"] },
        },
      ],
      descarte: { cosmeticas: 2, fundadas: 1 },
      fechas: [
        {
          title: "Cierre de registro",
          when: "27 oct.",
          estado: "proxima",
          fecha: "2026-10-27",
        },
        {
          title: "Vencido",
          when: "1 oct.",
          estado: "caducada",
          fecha: "2026-10-01",
        },
        { title: "Raro", when: "algún día", estado: "otro", fecha: null },
      ],
    },
    tarjetas: [
      {
        titulo: "A",
        hecho: "Hecho uno",
        por_que: "Porque uno",
        fuentes: ["news_rss", "news_rss", "x_twitter"],
        tono: "negativo",
        repeat: true,
        angulo_nuevo: "Nuevo ángulo",
      },
      {
        titulo: null,
        hecho: null,
        por_que: null,
        fuentes: [],
        tono: null,
        repeat: false,
      },
    ],
    campo: [
      {
        titulo: "Reporte",
        contenido: "Texto",
        lugar: "Angelópolis",
        cuando: null,
        estado: "publicada",
      },
      { titulo: "Otro", estado: "en revisión" },
    ],
  };
}

describe("hasDigestV3", () => {
  it("is false for legacy v2 rows", () => {
    expect(hasDigestV3(v2Content())).toBe(false);
    expect(hasDigestV3(null)).toBe(false);
  });

  it("is true when any v3 key is present", () => {
    expect(hasDigestV3(v3Content())).toBe(true);
    expect(hasDigestV3({ campo: [] } as unknown as DailySummaryContent)).toBe(
      false,
    );
    expect(hasDigestV3({ campo: [{}] } as unknown as DailySummaryContent)).toBe(
      true,
    );
  });
});

describe("digestV3View", () => {
  it("returns null for v2 rows", () => {
    expect(digestV3View(v2Content())).toBeNull();
  });

  it("projects brief and tarjetas", () => {
    const view = digestV3View(v3Content());
    expect(view?.headline).toBe("Titular del día");
    expect(view?.delta).toHaveLength(2);
    // Legacy strings normalize: «Nueva historia:» prefix stripped, tone
    // note split into giro.
    expect(view?.delta[0]).toEqual({ titulo: "A", giro: null });
    expect(view?.delta[1]).toEqual({
      titulo: "B",
      giro: "el tono pasa de positivo a negativo",
    });
    // Typed rows (post 25/oct) pass through untouched.
    const typed = digestV3View({
      ...v3Content(),
      brief: {
        ...v3Content().brief,
        delta: [{ titulo: "C", giro: "el tono pasa de neutral a negativo" }],
      },
    });
    expect(typed?.delta).toEqual([
      { titulo: "C", giro: "el tono pasa de neutral a negativo" },
    ]);
    expect(view?.decisiones).toMatchObject([
      { titulo: "A", razon: "Impacto presupuestal", afectacion: null },
    ]);
    // Index 1 has no titulo: the fallback keeps the pick renderable.
    expect(view?.ruido).toMatchObject([{ titulo: "#1", razon: null, afectacion: null }]);
    expect(view?.aFavor).toEqual([]);
    expect(view?.fechas.map((fecha) => fecha.estado)).toEqual([
      "Próxima",
      "Caducada",
      "otro",
    ]);
    expect(view?.tarjetas[0]).toMatchObject({
      titulo: "A",
      hecho: "Hecho uno",
      porQue: "Porque uno",
      fuentes: ["news_rss", "news_rss", "x_twitter"],
      tono: "negativo",
      repeat: true,
      anguloNuevo: "Nuevo ángulo",
    });
  });

  it("projects the F5 riesgo bucket alongside the picks", () => {
    const view = digestV3View(v3Content());
    expect(view?.riesgos).toMatchObject([
      {
        titulo: "A",
        razon: "tono negativo dominante",
        afectacion: "Quién: Rectora Cedillo"
      }
    ]);
    // Legacy rows without the key degrade to empty, never error.
    const legacy = digestV3View({ ...v2Content(), brief: {}, tarjetas: [] });
    expect(legacy?.riesgos).toEqual([]);
  });

  it("projects F7 vigilancia lines with humanized fecha", () => {
    const view = digestV3View(v3Content());
    expect(view?.vigilancia).toHaveLength(1);
    const linea = view?.vigilancia[0];
    expect(linea?.persona).toBe("Lilia Cedillo");
    expect(linea?.nota).toBe("Critican la gestión de becas");
    expect(linea?.afectacion).toBe("Quién: Lilia Cedillo");
    expect(linea?.fecha).toContain("2026");
    // Malformed entries never break the view.
    const roto = digestV3View({
      ...v2Content(),
      brief: { vigilancia: [{ nota: "sin persona" }, "x"] } as never,
      tarjetas: []
    });
    expect(roto?.vigilancia).toEqual([]);
  });

  it("projects the F3 descarte line, never fabricated", () => {
    expect(digestV3View(v3Content())?.descarte).toBe(
      "Descartado: 2 actualizaciones cosméticas, 1 historia fundida",
    );
    const soloFundadas = digestV3View({
      ...v2Content(),
      brief: { descarte: { fundadas: 1 } },
      tarjetas: [],
    });
    expect(soloFundadas?.descarte).toBe("Descartado: 1 historia fundida");
    // Absent/zero/malformed descarte: no line, never a placeholder.
    const sinDescarte = digestV3View({
      ...v2Content(),
      brief: {},
      tarjetas: [],
    });
    expect(sinDescarte?.descarte).toBeNull();
    const cero = digestV3View({
      ...v2Content(),
      brief: { descarte: { cosmeticas: 0, fundadas: 0 } },
      tarjetas: [],
    });
    expect(cero?.descarte).toBeNull();
  });

  it("degrades per key: empty sections stay empty, never fabricated", () => {
    const view = digestV3View({
      ...v2Content(),
      brief: { headline: null },
      tarjetas: [{ titulo: "Solo titulo" } as never],
      campo: [],
    });
    expect(view?.headline).toBeNull();
    expect(view?.delta).toEqual([]);
    expect(view?.decisiones).toMatchObject([]);
    expect(view?.descarte).toBeNull();
    expect(view?.tarjetas).toMatchObject([
      {
        titulo: "Solo titulo",
        hecho: null,
        porQue: null,
        fuentes: [],
        tono: null,
        repeat: false,
        anguloNuevo: null,
      },
    ]);
  });
});

it('preserves raw object identity and compiled bullet positions before display filtering', () => {
  const raw = { titulo: 'Compilación', notas: ['B', '', 'A'], source_refs: [0, 1], notas_refs: [{ source_refs: [1] }, {}, { source_refs: [0] }], provenance: { notas: ['b', null, 'a'] } };
  const pick = { index: 1, razon: ' Razón cruda ', categoria: 'decision' as const };
  const view = digestV3View({ brief: { decisiones: [pick] }, tarjetas: [null as never, raw] });
  expect(view?.tarjetas[0].raw).toBe(raw);
  expect(view?.tarjetas[0].notas?.map(nota => nota.position)).toEqual([0, 2]);
  expect(view?.decisiones[0].raw).toBe(pick);
  expect(view?.decisiones[0].sourceRefs).toBe(raw.source_refs);
  expect(view?.decisiones[0].razon).toBe('Razón cruda');
});

it('reads new compiled metrics by raw position without mutating bindings or borrowing union counts', () => {
  const metric = (count: number) => ({ media_diversity: { identified_outlet_count: count }, veracity: 'not_evaluated' });
  const raw = { titulo: 'También hoy', notas: ['B', '', 'A'], notas_indicators: [metric(1), metric(9), metric(0)],
    source_refs: [0, 1], notas_refs: [{ source_refs: [1] }, {}, { source_refs: [0] }], ...metric(99) };
  const original = JSON.stringify(raw);
  const view = digestV3View({ indicators_version: 1, tarjetas: [raw] })!;
  expect(view.tarjetas[0].raw).toBe(raw);
  expect(view.tarjetas[0].indicators).toBeUndefined();
  expect(view.tarjetas[0].notas?.map(note => [note.position, note.indicators])).toEqual([
    [0, expect.objectContaining({ kind: 'new', count: 1 })],
    [2, expect.objectContaining({ kind: 'new', count: 0 })]
  ]);
  expect(JSON.stringify(raw)).toBe(original);
});
