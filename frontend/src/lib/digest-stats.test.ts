import { describe, expect, it } from 'vitest';

import { categoryRows, focusPersonLabel, monogram, negativeNewsItems, toneRows } from './digest-stats';

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
		// Equal counts fall back to alphabetical order; labels localized.
		expect(rows).toEqual([
			{ key: 'culture', label: 'Cultura', count: 1, pct: 25 },
			{ key: 'institutional', label: 'Institucional', count: 1, pct: 25 }
		]);
	});

	it('localizes the known classifier topics to Spanish', () => {
		const rows = categoryRows({
			institutional: 2,
			academic: 1,
			culture: 1,
			infrastructure: 1,
			students: 1,
			health: 1,
			sports: 1,
			finance: 1
		});
		expect(rows.map((row) => [row.key, row.label])).toEqual([
			['institutional', 'Institucional'],
			['academic', 'Académica'],
			['culture', 'Cultura'],
			['finance', 'Finanzas'],
			['health', 'Salud'],
			['infrastructure', 'Infraestructura'],
			['sports', 'Deportes'],
			['students', 'Estudiantes']
		]);
	});

	it('title-cases unknown topics instead of leaking raw keys', () => {
		const rows = categoryRows({ prensa: 1, opiniOn: 1 });
		expect(rows.map((row) => row.label)).toEqual(['Opinion', 'Prensa']);
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

describe('negativeNewsItems', () => {
	it('keeps only strict negative majorities, worst first', () => {
		const items = negativeNewsItems([
			// Event 1: 2 negative vs 1 positive → majority negative.
			{ event_id: 1, sentiment: 'negative', title: 'A', source: 'news_rss', published_at: '2026-10-19T08:00:00Z' },
			{ event_id: 1, sentiment: 'negative', title: 'A', source: 'gdelt', published_at: '2026-10-19T09:00:00Z' },
			{ event_id: 1, sentiment: 'positive', title: 'A', source: 'x_twitter', published_at: '2026-10-19T07:00:00Z' },
			// Event 2: tie → not majority.
			{ event_id: 2, sentiment: 'negative', title: 'B', source: 'news_rss' },
			{ event_id: 2, sentiment: 'positive', title: 'B', source: 'gdelt' },
			// Event 3: negative but unclassified majority? only one row.
			{ event_id: 3, sentiment: 'negative', title: 'C', source: 'news_rss' }
		]);
		expect(items.map((item) => item.event_id)).toEqual([1, 3]);
		// Source/date ride the newest mention of the event.
		expect(items[0].source).toBe('gdelt');
		expect(items[0].published_at).toBe('2026-10-19T09:00:00Z');
	});

	it('ignores unclassified rows, events without id and titleless events', () => {
		const items = negativeNewsItems([
			{ event_id: null, sentiment: 'negative', title: 'loose', source: 'news_rss' },
			{ event_id: 5, sentiment: 'negative', source: 'news_rss' },
			{ event_id: 6, sentiment: null, title: 'sin tono', source: 'news_rss' }
		]);
		expect(items).toEqual([]);
	});
});

describe('focusPersonLabel', () => {
	it('prefers the content stamp and falls back to the persona chain', () => {
		const content = {
			rectora: { person_id: 7 },
			personas: [{ person_id: 7, name: 'Lilia Cedillo Ramírez' }]
		};
		expect(focusPersonLabel({ rectora: { name: 'Estampada' } })).toBe('Estampada');
		expect(focusPersonLabel(content)).toBe('Lilia Cedillo Ramírez');
		expect(focusPersonLabel({ rectora: {} })).toBeNull();
		expect(focusPersonLabel(undefined)).toBeNull();
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
