/**
 * digest-brief-v3 (PR2): view model for the brief/evidencia/campo render.
 *
 * The backend esqueleto (builder.py) owns the shape; this module only
 * decides WHETHER the row carries the v3 keys and projects them into
 * presentational view models. Legacy v2 rows (no brief/tarjetas/campo)
 * yield `null` and the home keeps its layout untouched — degradation is
 * per key, so a partial row renders only the sections it actually has.
 */

import type {
  DailySummaryContent,
  DigestBriefFecha,
  DigestTarjeta,
} from "$lib/api";

/** True when the content carries any digest-brief-v3 key. */
export function hasDigestV3(
  content: DailySummaryContent | null | undefined,
): boolean {
  if (!content || typeof content !== "object") return false;
  const record = content as Record<string, unknown>;
  const brief = record.brief;
  if (brief !== null && typeof brief === "object") return true;
  return hasEntries(record.tarjetas) || hasEntries(record.campo);
}

function hasEntries(value: unknown): value is unknown[] {
  return Array.isArray(value) && value.length > 0;
}

/** Headline of a brief pick, resolved against the tarjeta pool. */
export interface BriefEntryView {
  titulo: string;
  razon: string | null;
}

export interface BriefFechaView {
  titulo: string;
  cuando: string;
  /** Human label for the caducada/proxima estado; unknown values pass through. */
  estado: string;
}

export interface TarjetaView {
  titulo: string | null;
  hecho: string | null;
  porQue: string | null;
  /** Source labels already humanized; empty when the card cites none. */
  fuentes: string[];
  tono: string | null;
  repeat: boolean;
  anguloNuevo: string | null;
}

export interface DigestV3View {
	headline: string | null;
	delta: string[];
	decisiones: BriefEntryView[];
	riesgos: BriefEntryView[];
	ruido: BriefEntryView[];
	aFavor: BriefEntryView[];
	fechas: BriefFechaView[];
	tarjetas: TarjetaView[];
	/** F3 visible discard line; null when the row reports no descarte. */
	descarte: string | null;
}

const FECHA_ESTADO_LABELS: Record<string, string> = {
  caducada: "Caducada",
  proxima: "Próxima",
};

function tituloOf(
  entry: Record<string, unknown> | undefined,
  fallback: string,
): string {
  const titulo = entry?.titulo ?? entry?.title;
  return typeof titulo === "string" && titulo.trim() ? titulo.trim() : fallback;
}

function textOrNull(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

/** Brief picks resolved to `{titulo, razon}` against the tarjetas. */
function seleccionView(
  entries: unknown,
  tarjetas: DigestTarjeta[],
): { titulo: string; razon: string | null }[] {
  if (!hasEntries(entries)) return [];
  const view: { titulo: string; razon: string | null }[] = [];
  for (const entry of entries) {
    if (!entry || typeof entry !== "object") continue;
    const record = entry as Record<string, unknown>;
    const index = record.index;
    const fuente =
      typeof index === "number" && Number.isInteger(index) && index >= 0
        ? tarjetas[index]
        : undefined;
    const titulo = tituloOf(
      fuente as Record<string, unknown> | undefined,
      typeof index === "number" ? `#${index}` : "Nota",
    );
    const razon = textOrNull(record.razon);
    if (!titulo && !razon) continue;
    view.push({ titulo, razon });
  }
  return view;
}

function tarjetaView(tarjeta: DigestTarjeta): TarjetaView {
  const record = tarjeta as unknown as Record<string, unknown>;
  const fuentes = hasEntries(tarjeta.fuentes)
    ? tarjeta.fuentes.filter(
        (fuente): fuente is string => typeof fuente === "string",
      )
    : [];
  return {
    titulo: textOrNull(record.titulo ?? record.title),
    hecho: textOrNull(record.hecho ?? record.summary),
    porQue: textOrNull(record.por_que),
    fuentes,
    tono: textOrNull(record.tono),
    repeat: tarjeta.repeat === true,
    anguloNuevo: textOrNull(record.angulo_nuevo),
  };
}

/** F3: the visible discard line, mirrored from the builder's label. */
function descarteLabel(descarte: unknown): string | null {
  if (!descarte || typeof descarte !== "object") return null;
  const record = descarte as Record<string, unknown>;
  const cosmeticas =
    typeof record.cosmeticas === "number" ? record.cosmeticas : 0;
  const fundadas = typeof record.fundadas === "number" ? record.fundadas : 0;
  if (cosmeticas <= 0 && fundadas <= 0) return null;
  const partes: string[] = [];
  if (cosmeticas > 0) {
    partes.push(
      `${cosmeticas} ${cosmeticas === 1 ? "actualización cosmética" : "actualizaciones cosméticas"}`,
    );
  }
  if (fundadas > 0) {
    partes.push(
      `${fundadas} ${fundadas === 1 ? "historia fundida" : "historias fundidas"}`,
    );
  }
  return `Descartado: ${partes.join(", ")}`;
}

/**
 * The full v3 view model, or `null` for legacy rows. Every list degrades to
 * empty on its own: the render gates each section on real data.
 */
export function digestV3View(
  content: DailySummaryContent,
): DigestV3View | null {
  if (!hasDigestV3(content)) return null;
  const record = content as Record<string, unknown>;
  const brief =
    record.brief && typeof record.brief === "object"
      ? (record.brief as Record<string, unknown>)
      : {};
  const tarjetas = hasEntries(record.tarjetas)
    ? (record.tarjetas as DigestTarjeta[])
    : [];

  const fechas: BriefFechaView[] = [];
  if (hasEntries(brief.fechas)) {
    for (const raw of brief.fechas as DigestBriefFecha[]) {
      if (!raw || typeof raw !== "object") continue;
      const recordFecha = raw as Record<string, unknown>;
      const titulo = textOrNull(recordFecha.title);
      const cuando = textOrNull(recordFecha.when);
      if (!titulo && !cuando) continue;
      const estadoKey = textOrNull(recordFecha.estado)?.toLowerCase() ?? "";
      fechas.push({
        titulo: titulo ?? "(sin título)",
        cuando: cuando ?? "",
        estado:
          FECHA_ESTADO_LABELS[estadoKey] ??
          textOrNull(recordFecha.estado) ??
          "Fecha",
      });
    }
  }

  return {
    headline: textOrNull(brief.headline),
    delta: hasEntries(brief.delta)
      ? (brief.delta as unknown[]).filter(
          (line): line is string => typeof line === "string",
        )
      : [],
    decisiones: seleccionView(brief.decisiones, tarjetas),
    riesgos: seleccionView(brief.riesgos, tarjetas),
    ruido: seleccionView(brief.ruido, tarjetas),
    aFavor: seleccionView(brief.a_favor, tarjetas),
    fechas,
    tarjetas: tarjetas.filter(Boolean).map(tarjetaView),
    descarte: descarteLabel(brief.descarte),
  };
}
