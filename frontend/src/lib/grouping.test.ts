import { describe, expect, it } from 'vitest';
import { groupByEvent } from './grouping';
import type { Mention } from './api';

function mention(id: number, eventId?: number, eventTitle?: string): Mention {
	return {
		id,
		keyword_id: null,
		source: 'news_rss',
		external_id: null,
		url: `https://example.com/${id}`,
		title: `Mencion ${id}`,
		content: null,
		author: null,
		lang: 'es',
		published_at: null,
		ingested_at: '2026-10-16T00:00:00Z',
		sentiment: null,
		sentiment_score: null,
		summary: null,
		reach: null,
		classifications: [],
		event_id: eventId ?? null,
		event_title: eventTitle ?? null
	} as Mention;
}

describe('groupByEvent', () => {
	it('keeps eventless mentions as single groups', () => {
		const groups = groupByEvent([mention(1), mention(2)]);
		expect(groups).toHaveLength(2);
		expect(groups.every((g) => g.event === null)).toBe(true);
	});

	it('collapses mentions sharing an event, first occurrence order preserved', () => {
		const groups = groupByEvent([
			mention(1, 7, 'Evento siete'),
			mention(2),
			mention(3, 7, 'Evento siete')
		]);
		expect(groups).toHaveLength(2);
		const first = groups[0];
		expect(first.key).toBe('event:7');
		expect(first.event).toEqual({ id: 7, title: 'Evento siete' });
		expect(first.mentions.map((m) => m.id)).toEqual([1, 3]);
	});

	it('leaves singleton event groups intact for the component to render plain', () => {
		const groups = groupByEvent([mention(1, 9, 'Solo')]);
		expect(groups).toHaveLength(1);
		expect(groups[0].mentions).toHaveLength(1);
	});

	it('falls back to a synthetic title when event_title is missing', () => {
		const groups = groupByEvent([mention(1, 9), mention(2, 9)]);
		expect(groups[0].event?.title).toBe('Evento 9');
	});
});
