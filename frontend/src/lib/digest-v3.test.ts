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
      decisiones: [
        { index: 0, categoria: "decision", razon: "Impacto presupuestal" },
      ],
      ruido: [{ index: 1, categoria: "ruido" }],
      a_favor: [],
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
    expect(view?.decisiones).toEqual([
      { titulo: "A", razon: "Impacto presupuestal" },
    ]);
    // Index 1 has no titulo: the fallback keeps the pick renderable.
    expect(view?.ruido).toEqual([{ titulo: "#1", razon: null }]);
    expect(view?.aFavor).toEqual([]);
    expect(view?.fechas.map((fecha) => fecha.estado)).toEqual([
      "Próxima",
      "Caducada",
      "otro",
    ]);
    expect(view?.tarjetas[0]).toEqual({
      titulo: "A",
      hecho: "Hecho uno",
      porQue: "Porque uno",
      fuentes: ["news_rss", "news_rss", "x_twitter"],
      tono: "negativo",
      repeat: true,
      anguloNuevo: "Nuevo ángulo",
    });
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
    expect(view?.decisiones).toEqual([]);
    expect(view?.descarte).toBeNull();
    expect(view?.tarjetas).toEqual([
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
