import { describe, expect, it } from 'vitest';

import { categoryRows, combineTones, monogram, splitTones, toneRows } from './digest-stats';

describe('splitTones', () => {
	it('splits news sources from social ones', () => {
		const { media, social } = splitTones([
			{ sentiment: 'positive', source: 'news_rss' },
			{ sentiment: null, source: 'gdelt' },
			{ sentiment: 'negative', source: 'x_twitter' },
			{ sentiment: 'neutral', source: 'facebook_page' }
		]);
		expect(media.total).toBe(2);
		expect(media.positive).toBe(1);
		expect(media.unclassified).toBe(1);
		expect(social.total).toBe(2);
		expect(social.negative).toBe(1);
		expect(social.neutral).toBe(1);
	});
});

describe('toneRows', () => {
	it('falls back to the given label without counts', () => {
		expect(toneRows(undefined, 'Sin datos')).toEqual([
			{ key: 'positive', label: 'Positiva', value: 'Sin datos' },
			{ key: 'negative', label: 'Negativa', value: 'Sin datos' },
			{ key: 'neutral', label: 'Neutra', value: 'Sin datos' }
		]);
	});

	it('renders counts when the bucket has data', () => {
		const rows = toneRows(
			{ positive: 2, negative: 0, neutral: 1, unclassified: 0, total: 3 },
			'Sin calcular'
		);
		expect(rows.map((row) => row.value)).toEqual(['2', '0', '1']);
	});
});

describe('categoryRows', () => {
	it('computes percentages over the explicit total', () => {
		const rows = categoryRows({ institutional: 1, culture: 1 }, 4);
		// Equal counts fall back to alphabetical order.
		expect(rows).toEqual([
			{ key: 'culture', label: 'culture', count: 1, pct: 25 },
			{ key: 'institutional', label: 'institutional', count: 1, pct: 25 }
		]);
	});

	it('drops empty topics and sorts by count', () => {
		const rows = categoryRows({ a: 1, b: 3, c: 0 });
		expect(rows.map((row) => row.key)).toEqual(['b', 'a']);
		expect(rows[0].pct).toBe(75);
	});

	it('returns empty without data', () => {
		expect(categoryRows(undefined)).toEqual([]);
		expect(categoryRows({ a: 0 })).toEqual([]);
	});
});

describe('combineTones', () => {
	it('adds every bucket', () => {
		const total = combineTones(
			{ positive: 1, negative: 2, neutral: 3, unclassified: 4, total: 10 },
			{ positive: 5, negative: 0, neutral: 0, unclassified: 0, total: 5 }
		);
		expect(total).toEqual({
			positive: 6,
			negative: 2,
			neutral: 3,
			unclassified: 4,
			total: 15
		});
	});
});

describe('monogram', () => {
	it('takes initials of the first two words', () => {
		expect(monogram('Lilia Cedillo Ramírez')).toBe('LC');
	});

	it('uses two letters for single-word names', () => {
		expect(monogram('BUAP')).toBe('BU');
	});

	it('degrades gracefully without letters', () => {
		expect(monogram('   ')).toBe('–');
	});
});
