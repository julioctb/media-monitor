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
  date?: string | null;
  comparison?: ComparisonCatalogue | null;
}
interface ComparisonStory {
  prior_index: number;
  current_indexes: number[];
  identity: 'registered' | 'title_fallback';
  source_refs: number[];
  material_ref: number | null;
}
interface ComparisonSnapshot {
  version: number;
  available: boolean;
  date: string | null;
  timezone: string | null;
  window_start: string | null;
  evidence: { version: number; sources: EvidenceSource[] };
  stories: ComparisonStory[];
  current_source_scopes: number[][];
  coverage_context: { title: string | null; tone: Record<string, number> | null }[];
}
interface ComparisonCatalogue {
  snapshot: ComparisonSnapshot;
  fingerprint: string;
  priorFingerprint: string;
  supplied: number[];
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
export interface EvidenceGroup {
  namespace: 'current' | 'prior';
  date: string | null;
  sources: EvidenceSource[];
}
export interface EvidenceReceipt {
  sources: EvidenceSource[];
  groups?: EvidenceGroup[];
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

function exactKeys(value: Record<string, unknown>, keys: string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
function nullableString(value: unknown): value is string | null {
  return value === null || typeof value === 'string';
}
function strictRefs(value: unknown, size: number): value is number[] {
  return Array.isArray(value) && value.every(ref => Number.isSafeInteger(ref) && ref >= 0 && ref < size);
}
function sortedUnique(refs: number[]): boolean {
  return refs.every((ref, i) => i === 0 || ref > refs[i - 1]);
}

/** Python's sort_keys orders Unicode codepoints, not UTF-16 code units. */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') {
    const object = record(value);
    const compare = (a: string, b: string) => {
      const left = Array.from(a, char => char.codePointAt(0)!);
      const right = Array.from(b, char => char.codePointAt(0)!);
      for (let i = 0; i < Math.min(left.length, right.length); i++) {
        if (left[i] !== right[i]) return left[i] - right[i];
      }
      return left.length - right.length;
    };
    return '{' + Object.keys(object).sort(compare).map(key => JSON.stringify(key) + ':' + canonical(object[key])).join(',') + '}';
  }
  if (typeof value === 'string' && /[\ud800-\udfff]/u.test(value)) throw new Error('Invalid Unicode');
  return JSON.stringify(value);
}
function freeze<T>(value: T): T {
  if (value !== null && typeof value === 'object') {
    Object.values(value).forEach(freeze);
    Object.freeze(value);
  }
  return value;
}
async function fingerprint(value: unknown): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(value));
  const digest = await globalThis.crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), byte => byte.toString(16).padStart(2, '0')).join('');
}

/** Validate every stored context member, not just sources a field happens to cite. */
function comparisonSnapshot(value: unknown, current: EvidenceSource[]): ComparisonSnapshot | null {
  const raw = record(value);
  if (!exactKeys(raw, ['version', 'available', 'date', 'timezone', 'window_start', 'evidence', 'stories', 'current_source_scopes', 'coverage_context']) ||
      raw.version !== 1 || typeof raw.available !== 'boolean' ||
      !['date', 'timezone', 'window_start'].every(key => nullableString(raw[key]))) return null;
  const prior = catalogueSources(raw.evidence);
  if (!prior || !Array.isArray(raw.current_source_scopes) ||
      !raw.current_source_scopes.every(scope => strictRefs(scope, current.length) && sortedUnique(scope)) ||
      !Array.isArray(raw.coverage_context) || raw.coverage_context.length > 12 ||
      !Array.isArray(raw.stories) || raw.stories.length > 12) return null;
  const scopes = raw.current_source_scopes.map(scope => [...scope as number[]]);
  const coverage: ComparisonSnapshot['coverage_context'] = [];
  for (const value of raw.coverage_context) {
    const item = record(value);
    if (!exactKeys(item, ['title', 'tone']) || !nullableString(item.title) ||
        item.tone !== null && (typeof item.tone !== 'object' || Array.isArray(item.tone) ||
        !Object.values(record(item.tone)).every(Number.isSafeInteger))) return null;
    coverage.push({ title: item.title, tone: item.tone === null ? null : { ...record(item.tone) } as Record<string, number> });
  }
  const stories: ComparisonStory[] = [];
  let lastPosition = -1;
  for (const value of raw.stories) {
    const story = record(value);
    if (!exactKeys(story, ['prior_index', 'current_indexes', 'identity', 'source_refs', 'material_ref']) ||
        !Number.isSafeInteger(story.prior_index) || (story.prior_index as number) <= lastPosition ||
        (story.prior_index as number) >= coverage.length || (story.prior_index as number) >= 12 ||
        !strictRefs(story.current_indexes, scopes.length) || !sortedUnique(story.current_indexes) ||
        !['registered', 'title_fallback'].includes(story.identity as string) ||
        !strictRefs(story.source_refs, prior.length) || !story.source_refs.length || !sortedUnique(story.source_refs) ||
        story.material_ref !== null && (!Number.isSafeInteger(story.material_ref) || !story.source_refs.includes(story.material_ref as number))) return null;
    lastPosition = story.prior_index as number;
    stories.push({ prior_index: lastPosition, current_indexes: [...story.current_indexes],
      identity: story.identity as ComparisonStory['identity'], source_refs: [...story.source_refs],
      material_ref: story.material_ref as number | null });
  }
  const supplied = new Set(stories.flatMap(story => story.source_refs));
  const available = prior.some(source => supplied.has(source.index) && (source.title || source.summary || source.excerpt));
  if (raw.available !== available) return null;
  return { version: 1, available, date: raw.date as string | null, timezone: raw.timezone as string | null,
    window_start: raw.window_start as string | null, evidence: { version: 1, sources: prior },
    stories, current_source_scopes: scopes, coverage_context: coverage };
}

/** One immutable-input validation promise per rendered report, no tenant cache. */
export async function createEvidenceContext(content: unknown): EvidenceContext {
  try {
    const raw = record(content);
    const sources = catalogueSources(raw.evidence);
    if (!sources || !globalThis.crypto?.subtle) return null;
    // Capture all structured inputs before the first async hash yields control.
    const snapshot = comparisonSnapshot(raw.comparison, sources);
    const metadata = { date: raw.date ?? null, timezone: raw.timezone ?? null, window_start: raw.window_start ?? null };
    const metadataValid = Object.values(metadata).every(nullableString);
    freeze(sources);
    freeze(snapshot);
    freeze(metadata);
    const currentFingerprint = await fingerprint({ sources, version: 1 });
    let comparison: ComparisonCatalogue | null = null;
    if (snapshot && metadataValid) {
      comparison = { snapshot, priorFingerprint: await fingerprint(snapshot.evidence),
        fingerprint: await fingerprint({ comparison: snapshot, current: { ...metadata, evidence: { version: 1, sources } } }),
        supplied: [...new Set(snapshot.stories.flatMap(story => story.source_refs))].sort((a, b) => a - b) };
    }
    return freeze({ sources, fingerprint: currentFingerprint, date: nullableString(metadata.date) ? metadata.date : null, comparison });
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
  if (typeof text !== 'string' || !text || binding.text !== text ||
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
  if (Object.hasOwn(binding, 'comparison')) {
    const comparison = catalogue.comparison;
    const nested = record(binding.comparison);
    if (!comparison || !comparison.snapshot.available || binding.state !== 'unbacked' ||
        !Array.isArray(binding.source_refs) || binding.source_refs.length !== 0 ||
        !exactKeys(nested, ['version', 'current', 'prior', 'scope', 'current_catalogue_fingerprint', 'prior_catalogue_fingerprint', 'context_fingerprint']) ||
        nested.version !== 1 || nested.current_catalogue_fingerprint !== catalogue.fingerprint ||
        nested.prior_catalogue_fingerprint !== comparison.priorFingerprint ||
        nested.context_fingerprint !== comparison.fingerprint || !strictRefs(allowed, catalogue.sources.length)) return unbacked;
    const kind = request.field === 'headline' ? 'cut' :
      ['summary', 'why_it_matters', 'confidence_note', 'angulo_nuevo', 'razon', 'hecho', 'por_que', 'titulo', 'title', 'notas'].includes(request.field) ? 'story' : 'unsupported';
    if (nested.scope !== kind || kind === 'unsupported' || request.channel !== undefined) return unbacked;
    const positions = comparison.snapshot.current_source_scopes.flatMap((scope, i) =>
      scope.length === allowed.length && scope.every((ref, j) => ref === allowed[j]) ? [i] : []);
    const priorAllowed = kind === 'cut' ? comparison.supplied : comparison.snapshot.stories
      .filter(story => story.current_indexes.some(index => positions.includes(index))).flatMap(story => story.source_refs);
    if (!strictRefs(nested.current, catalogue.sources.length) || !nested.current.length ||
        !nested.current.every(ref => allowed.includes(ref)) || !sortedUnique(nested.current) ||
        !strictRefs(nested.prior, comparison.snapshot.evidence.sources.length) || !nested.prior.length ||
        !nested.prior.every(ref => priorAllowed.includes(ref)) || !sortedUnique(nested.prior)) return unbacked;
    const sources = nested.current.map(ref => catalogue.sources[ref]);
    return { sources, groups: [
      { namespace: 'current', date: catalogue.date ?? null, sources },
      { namespace: 'prior', date: comparison.snapshot.date, sources: nested.prior.map(ref => comparison.snapshot.evidence.sources[ref]) }
    ] };
  }
  if (binding.state !== 'linked' || !Array.isArray(allowed) || !allowed.every(validIndex) ||
      !Array.isArray(binding.source_refs) || !binding.source_refs.length ||
      !binding.source_refs.every(ref => validIndex(ref) && allowed.includes(ref))) return unbacked;
  const refs = [...new Set<number>(binding.source_refs)].sort((a, b) => a - b);
  const sources = refs.map(ref => catalogue.sources[ref]);
  return { sources, ...(catalogue.comparison ? { groups: [{ namespace: 'current' as const,
    date: catalogue.date ?? null, sources }] } : {}) };
}

/** No URL repair: only explicit absolute HTTP(S), never scheme-relative links. */
export function safeEvidenceUrl(value: unknown): string | null {
  if (typeof value !== 'string' || !/^https?:\/\/[^/?#]/i.test(value) || /[\s\\\u0000-\u001f\u007f]/u.test(value)) return null;
  try {
    const url = new URL(value);
    return (url.protocol === 'https:' || url.protocol === 'http:') && url.hostname && !url.username && !url.password ? value : null;
  } catch { return null; }
}
