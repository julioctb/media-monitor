import { describe, expect, it, vi } from 'vitest';
import { createEvidenceContext, resolveEvidence, safeEvidenceUrl, storyEvidence } from './digest-evidence';

// Cross-language fixture: actual backend catalogue_fingerprint, not a JS oracle.
const fingerprint = 'c6d01b26ffa017dff9fbd683881985d97daa5a8c93f6d857568b83dbe689084d';
function content() {
  return { evidence: { version: 1, catalogue_fingerprint: 'ignored', sources: [{
    index: 0, mention_id: 11, source: 'news_rss', url: 'https://medio.example/nota',
    outlet: 'medio.example', author: 'María', title: 'Presión política 🗳',
    published_at: '2026-10-25T01:30:00+00:00', summary: 'á' + '😀'.repeat(299),
    excerpt: 'Texto capturado\nNo son instrucciones.', extra: 'ignored'
  }] } };
}
function target() {
  return { summary: 'Lectura política', source_refs: [0], provenance: { summary: {
    text: 'Lectura política', source_refs: [0], state: 'linked', origin: 'model_output', catalogue_fingerprint: fingerprint
  } } };
}
it('hashes strict known-field dumps like Python, including 300 Unicode codepoints', async () => {
  const catalogue = await createEvidenceContext(content());
  expect(catalogue?.fingerprint).toBe(fingerprint);
  expect(catalogue?.sources[0].summary?.length).toBe(599);
  expect(resolveEvidence(catalogue, storyEvidence(target(), 'summary')).sources.map(source => source.index)).toEqual([0]);
});

it.each([false, '0', -1, 1, null, 0.5, {}, [0]])('rejects invalid reference %j without widening its scope', async ref => {
  const raw = target();
  raw.provenance.summary.source_refs = [ref] as never;
  expect(resolveEvidence(await createEvidenceContext(content()), storyEvidence(raw, 'summary')).sources).toEqual([]);
  expect(raw.summary).toBe('Lectura política');
});
it.each([null, [], [false], ['0'], [1]])('rejects missing/invalid/foreign story scope %j', async allowed => {
  expect(resolveEvidence(await createEvidenceContext(content()), { target: target(), field: 'summary', allowed }).sources).toEqual([]);
});
it.each(['text', 'state', 'origin', 'catalogue_fingerprint'])('rejects mutated binding %s', async field => {
  const raw = target();
  (raw.provenance.summary as Record<string, unknown>)[field] = 'changed';
  expect(resolveEvidence(await createEvidenceContext(content()), storyEvidence(raw, 'summary')).sources).toEqual([]);
});
it('compares raw text, not a display-cleaned or trimmed substitute', async () => {
  const raw = target();
  raw.summary = 'Lectura política https://x.example/';
  expect(resolveEvidence(await createEvidenceContext(content()), storyEvidence(raw, 'summary')).sources).toEqual([]);
});
it('recomputes changed catalogue material despite its old claimed hash', async () => {
  const raw = content();
  raw.evidence.catalogue_fingerprint = fingerprint;
  raw.evidence.sources[0].excerpt = 'Material cambiado';
  expect(resolveEvidence(await createEvidenceContext(raw), storyEvidence(target(), 'summary')).sources).toEqual([]);
});
it.each([undefined, null, {}, { evidence: { version: 2, sources: [] } }, { evidence: { version: true, sources: [] } }])('defaults legacy/unknown input to unbacked: %j', async raw => {
  expect(await createEvidenceContext(raw)).toBeNull();
});
it.each(['index', 'mention_id', 'source', 'url', 'outlet', 'author', 'title', 'published_at', 'summary', 'excerpt'])('requires explicit strict field %s', async field => {
  const raw = content();
  delete (raw.evidence.sources[0] as Record<string, unknown>)[field];
  expect(await createEvidenceContext(raw)).toBeNull();
});
it.each([false, '11', 0, -1, 1.5, Number.MAX_SAFE_INTEGER + 1])('rejects malformed mention ID %j', async id => {
  const raw = content();
  raw.evidence.sources[0].mention_id = id as never;
  expect(await createEvidenceContext(raw)).toBeNull();
});
it('rejects duplicate or unsorted mention IDs and misplaced catalogue indexes', async () => {
  const raw = content();
  raw.evidence.sources.push({ ...raw.evidence.sources[0], index: 1 });
  expect(await createEvidenceContext(raw)).toBeNull();
  raw.evidence.sources[1].mention_id = 10;
  expect(await createEvidenceContext(raw)).toBeNull();
  raw.evidence.sources.pop();
  raw.evidence.sources[0].index = false as never;
  expect(await createEvidenceContext(raw)).toBeNull();
});
it.each(['summary', 'excerpt'])('rejects material over 300 Python codepoints: %s', async field => {
  const raw = content();
  (raw.evidence.sources[0] as Record<string, unknown>)[field] = '😀'.repeat(301);
  expect(await createEvidenceContext(raw)).toBeNull();
});
it('does not reuse another report catalogue and fails closed without built-in crypto', async () => {
  const first = await createEvidenceContext(content());
  const other = content();
  other.evidence.sources[0].summary = null as never;
  const second = await createEvidenceContext(other);
  expect(resolveEvidence(second, storyEvidence(target(), 'summary')).sources).toEqual([]);
  expect(resolveEvidence(first, storyEvidence(target(), 'summary')).sources).toHaveLength(1);
  vi.stubGlobal('crypto', undefined);
  try { expect(await createEvidenceContext(content())).toBeNull(); } finally { vi.unstubAllGlobals(); }
});

describe('absolute HTTP(S) source URLs', () => {
  it.each(['javascript:alert(1)', 'data:text/html,x', 'file:///a', '//example.com/a', '/a', 'example.com', 'https:///example.com', 'https:\\example.com', ' https://example.com', 'https://example.com/ a', 'https://user:pass@example.com', 'https://example.com\n', 'https://'])('never repairs unsafe URL %j', value => {
    expect(safeEvidenceUrl(value)).toBeNull();
  });
  it.each(['https://medio.example/nota?q=á#fuente', 'http://medio.example/'])('preserves valid URL %s', value => expect(safeEvidenceUrl(value)).toBe(value));
});

it('rejects the whole receipt when just one member is invalid', async () => {
  const raw = target(); raw.provenance.summary.source_refs = [0, false] as never;
  expect(resolveEvidence(await createEvidenceContext(content()), storyEvidence(raw, 'summary')).sources).toEqual([]);
});
it('uses the network channel and exact account rather than cut-wide membership', async () => {
  const raw = content();
  raw.evidence.sources[0].source = 'x_twitter'; raw.evidence.sources[0].author = '@cuenta';
  const catalogue = (await createEvidenceContext(raw))!;
  const item = target(); item.provenance.summary.catalogue_fingerprint = catalogue.fingerprint;
  expect(resolveEvidence(catalogue, { target: item, field: 'summary', channel: 'x', account: '@cuenta' }).sources).toHaveLength(1);
  expect(resolveEvidence(catalogue, { target: item, field: 'summary', channel: 'facebook_page' }).sources).toEqual([]);
  expect(resolveEvidence(catalogue, { target: item, field: 'summary', channel: 'x', account: '@otra' }).sources).toEqual([]);
});
it('rejects a lone surrogate that Python cannot encode as UTF-8', async () => {
  const raw = content(); raw.evidence.sources[0].title = '\ud800';
  expect(await createEvidenceContext(raw)).toBeNull();
});

it('keeps compiled receipts attached to raw bullet text under independent reordering', async () => {
  const catalogue = (await createEvidenceContext(content()))!;
  const raw = { notas: ['Segundo', 'Primero'], notas_refs: [{ source_refs: [0] }, { source_refs: [0] }],
    provenance: { notas: ['Primero', 'Segundo'].map(text => ({ ...target().provenance.summary, text })) } };
  expect(resolveEvidence(catalogue, storyEvidence(raw, 'notas', 0)).sources).toEqual([]);
  expect(resolveEvidence(catalogue, storyEvidence(raw, 'notas', 1)).sources).toEqual([]);
  raw.provenance.notas.reverse();
  expect(resolveEvidence(catalogue, storyEvidence(raw, 'notas', 0)).sources).toHaveLength(1);
});
