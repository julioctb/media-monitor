import { describe, expect, it } from 'vitest';

import type { PersonDetail } from '$lib/api';
import {
	groupPersonTimeline,
	personDirectoryHref,
	personTimelinePage
} from './persons';

const item = (id: number, at: string): PersonDetail['timeline'][number] => ({
	mention_id: id,
	title: `Nota ${id}`,
	url: `https://example.com/${id}`,
	source: 'news_rss',
	published_at: at,
	ingested_at: at,
	sentiment: null,
	role: null,
	org: null,
	context: null,
	event_id: null,
	event_title: null,
	political_label: null
});

describe('persons presentation helpers', () => {
	it('builds an encoded directory search without stale pagination', () => {
		expect(personDirectoryHref('Lilia Cedillo & Rectoría')).toBe('/persons?q=Lilia+Cedillo+%26+Rector%C3%ADa');
	});

	it('groups timeline rows by display day while preserving API order', () => {
		const groups = groupPersonTimeline([
			item(1, '2026-10-28T02:30:00Z'),
			item(2, '2026-10-28T01:30:00Z'),
			item(3, '2026-10-26T18:00:00Z')
		]);
		expect(groups.map((group) => group.items.map((row) => row.mention_id))).toEqual([[1, 2], [3]]);
	});

	it('uses optional timeline metadata when present and safe page fallbacks when absent', () => {
		const explicit = personTimelinePage(
			{ timeline: [item(1, '2026-10-27T12:00:00Z')], timeline_total: 7, timeline_limit: 1, timeline_offset: 2 },
			{ limit: 25, offset: 0 }
		);
		expect(explicit).toMatchObject({ offset: 2, limit: 1, total: 7, hasPrevious: true, hasNext: true });

		const fallback = personTimelinePage(
			{ timeline: [item(1, '2026-10-27T12:00:00Z')] },
			{ limit: 1, offset: 0 }
		);
		expect(fallback).toMatchObject({ offset: 0, limit: 1, total: null, hasPrevious: false, hasNext: true });
		expect(fallback).not.toHaveProperty('historicalTotal');
	});
});
