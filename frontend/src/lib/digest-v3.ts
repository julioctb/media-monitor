/**
 * digest-brief-v3 (PR2): view model for the brief/evidencia/campo render.
 *
 * The backend esqueleto (builder.py) owns the shape; this module only
 * decides WHETHER the row carries the v3 keys and projects them into
 * presentational view models. Legacy v2 rows (no brief/tarjetas/campo)
 * yield `null` and the home keeps its layout untouched — degradation is
 * per key, so a partial row renders only the sections it actually has.
 */

import { formatDisplayDateTime } from "$lib/format";
import { readDigestIndicators, type DigestIndicators } from "$lib/digest-indicators";

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
  raw?: unknown;
  sourceRefs?: unknown;
  titulo: string;
  razon: string | null;
  accionSugerida?: string;
  condicion?: string;
  /** F6 structured afectacion, humanized; null when the entry carries none. */
  afectacion: string | null;
}

export interface VigilanciaView {
  persona: string;
  nota: string | null;
  fecha: string;
  afectacion: string | null;
}

export interface BriefFechaView {
  titulo: string;
  cuando: string;
  /** Human label for the caducada/proxima estado; unknown values pass through. */
  estado: string;
  /** Raw ISO date (YYYY-MM-DD) when the brief row carries one; null otherwise. */
  fechaIso: string | null;
}

export interface TarjetaView {
  raw?: DigestTarjeta;
  notas?: { text: string; position: number; indicators?: DigestIndicators }[];
  indicators?: DigestIndicators;
  analysisNote?: string | null;
  titulo: string | null;
  hecho: string | null;
  porQue: string | null;
  /** Source labels already humanized; empty when the card cites none. */
  fuentes: string[];
  tono: string | null;
  repeat: boolean;
  anguloNuevo: string | null;
}

export interface DeltaLineaView {
  titulo: string;
  /** Tone-shift note («el tono pasa de X a Y»); null on new-story lines. */
  giro: string | null;
}

export interface DigestV3View {
  headline: string | null;
  delta: DeltaLineaView[];
  decisiones: BriefEntryView[];
  riesgos: BriefEntryView[];
  ruido: BriefEntryView[];
  aFavor: BriefEntryView[];
  fechas: BriefFechaView[];
  vigilancia: VigilanciaView[];
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

/** F6 afectacion as one muted line; null when there is nothing to show. */
function afectacionLabel(afectacion: unknown): string | null {
  if (!afectacion || typeof afectacion !== "object") return null;
  const record = afectacion as Record<string, unknown>;
  const partes: string[] = [];
  if (Array.isArray(record.quien) && record.quien.length > 0) {
    const names = record.quien.filter(
      (n): n is string => typeof n === "string",
    );
    if (names.length > 0) partes.push(`Quién: ${names.join(", ")}`);
  }
  if (typeof record.trayectoria === "string" && record.trayectoria.trim()) {
    partes.push(`Trayectoria: ${record.trayectoria.trim()}`);
  }
  if (record.ventana && typeof record.ventana === "object") {
    const ventana = record.ventana as Record<string, unknown>;
    const cuando = typeof ventana.cuando === "string" ? ventana.cuando : "";
    const titulo = typeof ventana.titulo === "string" ? ventana.titulo : "";
    if (cuando || titulo)
      partes.push(`Ventana: ${[cuando, titulo].filter(Boolean).join(" — ")}`);
  }
  return partes.length > 0 ? partes.join(" · ") : null;
}

/**
 * Delta normalizer: new rows store `{titulo, giro}`; legacy rows (pre
 * 25/oct) store composed strings — «Nueva historia: X» and «X: el tono
 * pasa de A a B» — parsed here so every row renders the same way.
 */
function deltaLineaView(entry: unknown): DeltaLineaView | null {
  if (typeof entry === "string") {
    const giro = entry.match(/^(.*?): el tono pasa de /);
    if (giro?.[1]) {
      return { titulo: giro[1], giro: entry.slice(giro[1].length + 2) };
    }
    const prefijo = "Nueva historia: ";
    if (entry.startsWith(prefijo)) {
      return { titulo: entry.slice(prefijo.length), giro: null };
    }
    return { titulo: entry, giro: null };
  }
  if (entry && typeof entry === "object") {
    const record = entry as Record<string, unknown>;
    const titulo = textOrNull(record.titulo);
    if (!titulo) return null;
    return { titulo, giro: textOrNull(record.giro) };
  }
  return null;
}

function vigiliaView(entry: unknown): VigilanciaView | null {
  if (!entry || typeof entry !== "object") return null;
  const record = entry as Record<string, unknown>;
  const persona = textOrNull(record.persona);
  if (!persona) return null;
  const fechaRaw = textOrNull(record.fecha);
  return {
    persona,
    nota: textOrNull(record.nota),
    fecha: fechaRaw ? formatDisplayDateTime(fechaRaw) : "",
    afectacion: afectacionLabel(record.afectacion),
  };
}

/** Brief picks resolved to `{titulo, razon, afectacion}` against the tarjetas. */
function seleccionView(
  entries: unknown,
  tarjetas: DigestTarjeta[],
): BriefEntryView[] {
  if (!hasEntries(entries)) return [];
  const view: BriefEntryView[] = [];
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
    const accionSugerida = textOrNull(record.accion_sugerida);
    const condicion = textOrNull(record.condicion);
    const afectacion = afectacionLabel(record.afectacion);
    if (!titulo && !razon && !afectacion) continue;
    view.push({ titulo, razon, afectacion, raw: record, sourceRefs: fuente?.source_refs ?? null,
      ...(accionSugerida ? { accionSugerida } : {}), ...(condicion ? { condicion } : {}) });
  }
  return view;
}

function tarjetaView(tarjeta: DigestTarjeta, content: DailySummaryContent): TarjetaView {
  const record = tarjeta as unknown as Record<string, unknown>;
  const fuentes = hasEntries(tarjeta.fuentes)
    ? tarjeta.fuentes.filter(
        (fuente): fuente is string => typeof fuente === "string",
      )
    : [];
  return {
    raw: tarjeta,
    ...(!Array.isArray(record.notas) ? { indicators: readDigestIndicators(content, tarjeta) } : {}),
    ...(readDigestIndicators(content, tarjeta).kind === 'new' ? { analysisNote: textOrNull(record.confidence_note) } : {}),
    notas: Array.isArray(record.notas) ? record.notas.flatMap((text, position) =>
      typeof text === 'string' && text.trim() ? [{ text, position, indicators: readDigestIndicators(content, tarjeta, position) }] : []) : [],
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
        fechaIso: textOrNull(recordFecha.fecha),
      });
    }
  }

  return {
    headline: textOrNull(brief.headline),
    delta: hasEntries(brief.delta)
      ? (brief.delta as unknown[])
          .map(deltaLineaView)
          .filter((linea): linea is DeltaLineaView => linea !== null)
      : [],
    decisiones: seleccionView(brief.decisiones, tarjetas),
    riesgos: seleccionView(brief.riesgos, tarjetas),
    ruido: seleccionView(brief.ruido, tarjetas),
    aFavor: seleccionView(brief.a_favor, tarjetas),
    fechas,
    vigilancia: hasEntries(brief.vigilancia)
      ? (brief.vigilancia as unknown[])
          .map(vigiliaView)
          .filter((linea): linea is VigilanciaView => linea !== null)
      : [],
    tarjetas: tarjetas.filter(Boolean).map((tarjeta) => tarjetaView(tarjeta, content)),
    descarte: descarteLabel(brief.descarte),
  };
}
