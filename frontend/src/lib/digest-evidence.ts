/** Recorded publication provenance, never semantic or factual verification. */
export interface EvidenceSource {
  index: number;
  mention_id: number;
  source: string;
  url: string;
  outlet: string;
  author: string | null;
  title: string | null;
  published_at: string | null;
  summary: string | null;
  excerpt: string | null;
}

export interface EvidenceCatalogue {
  sources: EvidenceSource[];
  fingerprint: string;
}
export type EvidenceContext = Promise<EvidenceCatalogue | null>;
export interface EvidenceRequest {
  target?: unknown;
  field: string;
  /** Explicit raw text, notably the actual report narrative. */
  text?: unknown;
  /** Omitted: whole cut. Null/malformed: no valid scope. */
  allowed?: unknown;
  position?: number;
  channel?: string;
  account?: string;
}
export interface EvidenceReceipt {
  sources: EvidenceSource[];
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown> : {};
}
const sourceKeys = ['author', 'excerpt', 'index', 'mention_id', 'outlet', 'published_at', 'source', 'summary', 'title', 'url'] as const;
const nullableKeys = ['author', 'title', 'published_at', 'summary', 'excerpt'] as const;

/** Match Python strict known-field dumps, including codepoint material bounds. */
function catalogueSources(value: unknown): EvidenceSource[] | null {
  const catalogue = record(value);
  if (catalogue.version !== 1 || !Array.isArray(catalogue.sources)) return null;
  let previousId = 0;
  const sources: EvidenceSource[] = [];
  for (const [position, value] of catalogue.sources.entries()) {
    const source = record(value);
    if (source.index !== position || !Number.isSafeInteger(source.mention_id) ||
        (source.mention_id as number) <= previousId ||
        !['source', 'url', 'outlet'].every(key => typeof source[key] === 'string') ||
        !nullableKeys.every(key => source[key] === null || typeof source[key] === 'string') ||
        !['summary', 'excerpt'].every(key => source[key] === null ||
          Array.from(source[key] as string).length <= 300)) return null;
    // Lone UTF-16 surrogates cannot be encoded by Python's UTF-8 fingerprint.
    if (sourceKeys.some(key => typeof source[key] === 'string' && /[\ud800-\udfff]/u.test(source[key] as string))) return null;
    previousId = source.mention_id as number;
    // Sorted keys reproduce json.dumps(sort_keys=True); extra keys are excluded.
    sources.push(Object.fromEntries(sourceKeys.map(key => [key, source[key]])) as unknown as EvidenceSource);
  }
  return sources;
}

/** One immutable-input validation promise per rendered report, no tenant cache. */
export async function createEvidenceContext(content: unknown): EvidenceContext {
  try {
    const sources = catalogueSources(record(content).evidence);
    if (!sources || !globalThis.crypto?.subtle) return null;
    const canonical = JSON.stringify({ sources, version: 1 });
    const bytes = new TextEncoder().encode(canonical);
    const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
    const fingerprint = Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
    return { sources, fingerprint };
  } catch {
    // Unavailable crypto/unsupported data must never acquire linked status.
    return null;
  }
}

/** Story and compiled-bullet scope selection is centralized, never a union fallback. */
export function storyEvidence(target: unknown, field: string, position?: number): EvidenceRequest {
  const raw = record(target);
  const notes = raw.notas_refs;
  const scope = position === undefined ? raw : record(Array.isArray(notes) ? notes[position] : null);
  return { target, field, position, allowed: scope.source_refs ?? null };
}

/** All-or-nothing receipt validation against raw prose and actual frozen material. */
export function resolveEvidence(catalogue: EvidenceCatalogue | null, request: EvidenceRequest): EvidenceReceipt {
  const unbacked: EvidenceReceipt = { sources: [] };
  if (!catalogue) return unbacked;
  const target = record(request.target);
  const provenance = record(target.provenance);
  let text = request.text === undefined ? target[request.field] : request.text;
  let rawBinding = provenance[request.field];
  if (request.position !== undefined) {
    if (!Number.isSafeInteger(request.position) || request.position < 0) return unbacked;
    text = Array.isArray(text) ? text[request.position] : undefined;
    rawBinding = Array.isArray(rawBinding) ? rawBinding[request.position] : undefined;
  }
  const binding = record(rawBinding);
  if (typeof text !== 'string' || !text || binding.text !== text || binding.state !== 'linked' ||
      !['model_output', 'source_material', 'derived', 'revision_restore', 'fallback'].includes(binding.origin as string) ||
      binding.catalogue_fingerprint !== catalogue.fingerprint) return unbacked;
  let allowed = request.allowed === undefined ? catalogue.sources.map(source => source.index) : request.allowed;
  if (request.channel !== undefined) {
    const channel = request.channel === 'x' ? 'x_twitter' : request.channel;
    allowed = catalogue.sources.filter(source => source.source === channel &&
      (request.account === undefined || source.author === request.account)).map(source => source.index);
  }
  const validIndex = (index: unknown): index is number => Number.isSafeInteger(index) &&
    (index as number) >= 0 && (index as number) < catalogue.sources.length;
  if (!Array.isArray(allowed) || !allowed.every(validIndex) ||
      !Array.isArray(binding.source_refs) || !binding.source_refs.length ||
      !binding.source_refs.every(ref => validIndex(ref) && allowed.includes(ref))) return unbacked;
  const refs = [...new Set<number>(binding.source_refs)].sort((a, b) => a - b);
  return { sources: refs.map(ref => catalogue.sources[ref]) };
}

/** No URL repair: only explicit absolute HTTP(S), never scheme-relative links. */
export function safeEvidenceUrl(value: unknown): string | null {
  if (typeof value !== 'string' || !/^https?:\/\/[^/?#]/i.test(value) || /[\s\\\u0000-\u001f\u007f]/u.test(value)) return null;
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && url.hostname && !url.username && !url.password ? value : null;
  } catch { return null; }
}
