import { describe, expect, it } from 'vitest';
import { readDigestIndicators } from './digest-indicators';

const metric = (count: unknown) => ({
  media_diversity: { identified_outlet_count: count }, veracity: 'not_evaluated', confidence: 'alta'
});

describe('strict S7 indicator reader', () => {
  it('leaves genuinely historical confidence historical', () => {
    expect(readDigestIndicators({ noticias: [{ confidence: 'alta' }] }, { confidence: 'alta' })).toEqual({ kind: 'legacy' });
  });

  it.each([0, 1, 3])('retains the measured count %s without a confidence tier', (count) => {
    const result = readDigestIndicators({ indicators_version: 1 }, metric(count));
    expect(result).toMatchObject({ kind: 'new', count });
    if (result.kind === 'new') {
      expect(result.label).toContain('Diversidad de medios:');
      expect(result.label).toContain('Veracidad no evaluada');
      expect(result.label).not.toContain('alta');
    }
  });

  it.each([true, '3', -1, 0.5, Infinity, NaN, null, undefined])('rejects malformed count %s', (count) => {
    expect(readDigestIndicators({ indicators_version: 1 }, metric(count))).toMatchObject({ kind: 'new', count: null });
  });

  it.each([{}, { indicators_version: true }, { indicators_version: '1' }, { indicators_version: 2 }, { indicators_version: null }])('never falls back on malformed or missing version', (root) => {
    expect(readDigestIndicators(root, metric(3))).toMatchObject({ kind: 'new', count: null });
  });

  it.each([{ confidence: 'alta' }, { ...metric(0), veracity: 'verified' }, { veracity: 'not_evaluated' }])('fails closed for incomplete new fields', (target) => {
    expect(readDigestIndicators({ indicators_version: 1 }, target)).toMatchObject({ kind: 'new', count: null });
  });

  it('does not treat mixed new and old rows as historical high confidence', () => {
    const old = { confidence: 'alta' };
    expect(readDigestIndicators({ noticias: [metric(1), old] }, old)).toMatchObject({ kind: 'new', count: null });
    expect(readDigestIndicators({ tarjetas: [{ notas_indicators: [] }] }, old)).toMatchObject({ kind: 'new', count: null });
  });

  it('reads each raw compiled position and rejects misaligned metadata', () => {
    const card = { notas: ['primera', '', 'tercera'], notas_indicators: [metric(1), metric(9), metric(0)] };
    expect(readDigestIndicators({ indicators_version: 1 }, card, 2)).toMatchObject({ kind: 'new', count: 0 });
    expect(readDigestIndicators({ indicators_version: 1 }, { ...card, notas_indicators: [metric(9)] }, 0)).toMatchObject({ kind: 'new', count: null });
  });
});
