/** Strict shared read boundary: measured media diversity is not truth. */
export type DigestIndicators =
  | { kind: 'legacy' }
  | { kind: 'new'; count: number | null; label: string };

type RecordValue = Record<string, unknown>;
function record(value: unknown): RecordValue {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as RecordValue : {};
}

const KEYS = ['indicators_version', 'media_diversity', 'veracity', 'notas_indicators'];

export function readDigestIndicators(content: unknown, target: unknown, position?: number): DigestIndicators {
  const root = record(content);
  const row = record(target);
  const rows = [root, row, ...['noticias', 'tarjetas'].flatMap((key) =>
    Array.isArray(root[key]) ? root[key].map(record) : [])];
  if (!rows.some((entry) => KEYS.some((key) => Object.hasOwn(entry, key)))) {
    return { kind: 'legacy' };
  }
  const aligned = position === undefined || (
    Array.isArray(row.notas) && Array.isArray(row.notas_indicators) &&
    row.notas.length === row.notas_indicators.length && Number.isInteger(position) && position >= 0 && position < row.notas.length
  );
  const item = position === undefined ? row : record(aligned ? (row.notas_indicators as unknown[])[position] : null);
  const candidate = record(item.media_diversity).identified_outlet_count;
  const count = root.indicators_version === 1 && aligned && item.veracity === 'not_evaluated' &&
    typeof candidate === 'number' && Number.isSafeInteger(candidate) && candidate >= 0 ? candidate : null;
  const diversity = count === null ? 'no disponible' : `${count} ${count === 1 ? 'medio identificado' : 'medios identificados'}`;
  return { kind: 'new', count, label: `Diversidad de medios: ${diversity}. Veracidad no evaluada` };
}
