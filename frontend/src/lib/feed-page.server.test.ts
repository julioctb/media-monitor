import { afterEach, expect, it, vi } from 'vitest';

import { load } from '../routes/feed/+page.server';

/**
 * Channel pages fan out one query per source with the page's offset folded
 * into a single per-source pool. The API caps `limit` at 500
 * (backend/app/api/mentions.py `le=500`); a deeper pool 422s and the load
 * degrades to a null page, so every emitted mentions call must carry
 * limit <= 500 even at deep offsets.
 */

type RouteTable = Record<string, unknown>;

/** Stub fetch with a path-based router (query string ignored). */
function stubFetch(table: RouteTable) {
	const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
		const path = new URL(String(input), 'http://localhost').pathname;
		if (!(path in table)) throw new Error(`unrouted ${path}`);
		const body = table[path];
		if (body instanceof Response) return body;
		return new Response(JSON.stringify(body ?? null), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

/** Loader event stub: url + cookie jar (the mm_prefs reader). */
function route(url: string | URL, jar?: Record<string, string>) {
	return {
		url: new URL(url, 'http://localhost'),
		cookies: { get: (name: string) => jar?.[name] }
	} as never;
}

const metrics = {
	total: 96,
	by_source: { news_rss: 48, gdelt: 48 },
	by_sentiment: { negative: 96, positive: 0, neutral: 0, none: 0 },
	news_medium_count: 17,
	result_group_count: 63
};

it('loads metrics with the same effective filters as the direct result request', async () => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 200, x_twitter: 0 }, by_medium: { 'global.example': 200 }, news_medium_count: 40 },
		'/api/keywords': [],
		'/api/mentions': { items: [], total: 96 },
		'/api/stats/feed': metrics
	});
	const data = await load(route('http://localhost/feed?source=%20news_rss%20&channel=social&medium=%20alpha.example%20&sentiment=%20negative%20&keyword_id=0&political=1&q=budget%20%26%20tax&since=2026-10-14&until=2026-10-15&limit=1&offset=5&sort=ignored&sources=x_twitter'));
	const urls = fetchMock.mock.calls.map(([input]) => new URL(String(input)));
	const aggregate = urls.filter((u) => u.pathname === '/api/stats/feed');
	expect(aggregate).toHaveLength(1);
	const list = urls.find((u) => u.pathname === '/api/mentions')!;
	const expected = new URLSearchParams(list.search);
	expected.delete('limit');
	expected.delete('offset');
	// metrics keep the full tone distribution: the tone facet is excluded
	// (mockup toneFilterView counts feedBase(), not the tone-filtered list)
	expected.delete('sentiment');
	expect(aggregate[0].searchParams).toEqual(expected);
	expect(aggregate[0].searchParams.get('since')).toBe('2026-10-14T00:00:00-06:00');
	expect(aggregate[0].searchParams.get('until')).toBe('2026-10-15T23:59:59-06:00');
	expect(data).toMatchObject({ feedStats: metrics, feedStatsError: null, mentions: { total: 96 }, sourceCounts: { news_rss: 200, x_twitter: 0 }, mediumCounts: { 'global.example': 200 } });
});

it('aggregates a channel union once without summing source-distinct units', async () => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 0, gdelt: 0, x_twitter: 99, field_report: 3 } },
		'/api/keywords': [],
		'/api/stats/feed': metrics,
		'/api/mentions': { items: [], total: 48 }
	});
	const data = await load(route('http://localhost/feed?channel=news&sentiment=none&limit=1&offset=70'));
	const urls = fetchMock.mock.calls.map(([input]) => new URL(String(input)));
	const aggregates = urls.filter((u) => u.pathname === '/api/stats/feed');
	expect(aggregates).toHaveLength(1);
	expect(aggregates[0].searchParams.getAll('sources')).toEqual(['gdelt', 'news_rss']);
	expect(aggregates[0].searchParams.has('sentiment')).toBe(false);
	expect(aggregates[0].searchParams.has('source')).toBe(false);
	expect(aggregates[0].searchParams.has('limit')).toBe(false);
	expect(data).toMatchObject({ feedStats: metrics, mentions: { total: 96 }, channelGroups: { news: ['gdelt', 'news_rss'] } });
});

it('returns measured zeros for a known empty channel without querying all rows', async () => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 200, x_twitter: 30 } },
		'/api/keywords': [],
		'/api/stats/feed': metrics
	});
	const data = await load(route('http://localhost/feed?channel=field'));
	expect(fetchMock.mock.calls.map(([input]) => new URL(String(input)).pathname)).not.toContain('/api/stats/feed');
	expect(data).toMatchObject({ mentions: { items: [], total: 0 }, feedStats: { total: 0, news_medium_count: 0, result_group_count: 0, by_source: { news_rss: 0, x_twitter: 0 }, by_sentiment: { positive: 0, negative: 0, neutral: 0, none: 0 } }, feedStatsError: null });
});

it('keeps a successful list and its controls when only the aggregate is unavailable', async () => {
	const mentions = { items: [{ id: 1, title: 'Retained synthetic card' }], total: 96 };
	stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 200 }, news_medium_count: 40 },
		'/api/keywords': [],
		'/api/stats/feed': new Response(JSON.stringify({ detail: 'synthetic aggregate failure' }), { status: 503 }),
		'/api/mentions': mentions
	});
	const data = await load(route('http://localhost/feed?sentiment=negative&limit=1&offset=5'));
	expect(data).toMatchObject({ mentions, feedStats: null, feedStatsError: 'Indicadores no disponibles: synthetic aggregate failure', filters: { sentiment: 'negative', limit: 1, offset: 5 } });
});

it.each([
	['source=news_rss&channel=social', { source: 'news_rss' }],
	['medium=alpha.example&channel=field', { medium: 'alpha.example' }],
	['channel=social', { sources: ['x_twitter'] }],
	['channel=field', { sources: ['field_report'] }],
	['channel=unknown&sentiment=invalid&keyword_id=no&political=0', {}],
	['sentiment=none&keyword_id=0&political=1&q=%20budget%20', { keyword_id: '0', classifier: 'political', label: 'political', q: 'budget' }],
	['since=2026-10-15&until=2026-10-14', { since: '2026-10-15T00:00:00-06:00', until: '2026-10-14T23:59:59-06:00' }],
	['source=gdelt&source=news_rss&sentiment=negative&sentiment=positive', { source: 'gdelt' }],
	['sort=ignored&sources=gdelt&classifier=other&label=other&person_id=1&topic=other', {}]
])('keeps accepted filter semantics for %s', async (query, expected) => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 0, gdelt: 0, x_twitter: 0, field_report: 0 } },
		'/api/keywords': [], '/api/stats/feed': metrics,
		'/api/mentions': { items: [], total: 0 }
	});
	await load(route(`http://localhost/feed?${query}`));
	const aggregate = fetchMock.mock.calls.map(([input]) => new URL(String(input))).find((url) => url.pathname === '/api/stats/feed')!;
	const actual: Record<string, string | string[]> = Object.fromEntries(aggregate.searchParams);
	if (aggregate.searchParams.has('sources')) actual.sources = aggregate.searchParams.getAll('sources');
	expect(actual).toEqual(expected);
});

it.each(['/api/mentions', '/api/stats/overview'])('preserves existing fatal errors for %s', async (path) => {
	stubFetch({ '/api/stats/overview': { by_source: {} }, '/api/keywords': [], '/api/mentions': { items: [], total: 0 }, [path]: new Response(JSON.stringify({ detail: 'existing failure' }), { status: 422 }) });
	await expect(load(route('http://localhost/feed'))).rejects.toMatchObject({ status: 422, body: { message: 'No se pudo cargar el feed: existing failure' } });
});

it('keeps missing metrics unavailable rather than inventing a zero response', async () => {
	stubFetch({ '/api/stats/overview': { by_source: {} }, '/api/keywords': [], '/api/stats/feed': null, '/api/mentions': { items: [], total: 0 } });
	const data = await load(route('http://localhost/feed'));
	expect(data).toMatchObject({ feedStats: null, mentions: { items: [], total: 0 } });
});

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

it('keeps every channel pool call within the API limit at deep offsets', async () => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { elpopular: 12 } },
		'/api/keywords': [],
		'/api/stats/feed': metrics,
		'/api/mentions': { items: [], total: 0 }
	});

	const url = new URL('http://localhost/?channel=news&limit=200&offset=450');
	await load(route(url));

	const mentionCalls = fetchMock.mock.calls
		.map((call) => new URL(String(call[0]), 'http://localhost'))
		.filter((u) => u.pathname === '/api/mentions');
	expect(mentionCalls.length).toBeGreaterThan(0);
	for (const callUrl of mentionCalls) {
		const limit = Number(callUrl.searchParams.get('limit'));
		expect(limit).toBeLessThanOrEqual(500);
	}
});

it('forwards the medium facet as one direct query and echoes it in filters', async () => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: {}, by_medium: { 'e-consulta.com': 3, 'x.com': 1 } },
		'/api/keywords': [],
		'/api/stats/feed': metrics,
		'/api/mentions': { items: [], total: 0 }
	});

	const url = new URL('http://localhost/?channel=news&medium=e-consulta.com');
	const data = (await load(route(url))) as Record<string, Record<string, unknown>>;

	const mentionCalls = fetchMock.mock.calls
		.map((call) => new URL(String(call[0]), 'http://localhost'))
		.filter((u) => u.pathname === '/api/mentions');
	// medium wins over the channel pools: exactly one call, carrying medium.
	expect(mentionCalls).toHaveLength(1);
	expect(mentionCalls[0].searchParams.get('medium')).toBe('e-consulta.com');
	expect(mentionCalls[0].searchParams.get('channel')).toBeNull();
	expect((data.filters as Record<string, string>).medium).toBe('e-consulta.com');
	expect(data.mediumCounts).toEqual({ 'e-consulta.com': 3, 'x.com': 1 });
});

it('echoes the mm_prefs cookie and derives focus rows from followed events', async () => {
	const focusMentions = [
		{ id: 11, source: 'news_rss', url: 'https://a.example/11', title: 'En ventana', sentiment: null, published_at: '2026-10-14T18:30:00Z' },
		{ id: 12, source: 'x_twitter', url: 'https://a.example/12', title: 'Fuera de ventana', sentiment: null, published_at: '2026-10-20T18:30:00Z' }
	];
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 4 } },
		'/api/keywords': [],
		'/api/stats/feed': metrics,
		'/api/mentions': { items: [{ id: 1, event_id: 9 }], total: 1 },
		'/api/clients/1/events/9': {
			id: 9, title: 'Evento en foco', mention_count: 3, source_count: 2, summary: null,
			first_seen_at: '2026-10-13T10:00:00Z', last_seen_at: '2026-10-14T19:00:00Z',
			mentions: focusMentions
		},
		'/api/clients/1/events/404': new Response(JSON.stringify({ detail: 'gone' }), { status: 500 })
	});
	const data = (await load(
		route('http://localhost/feed?since=2026-10-14&until=2026-10-14', {
			mm_prefs: JSON.stringify({ saved: [7], follow: [9, 404], seen: { '9': 'stale' } })
		})
	)) as Record<string, unknown>;
	// cookie echoed for the client store seed, parsed tolerantly
	expect(data.prefs).toEqual({ saved: [7], follow: [9, 404], seen: { '9': 'stale' } });
	// focus = followed events with mentions inside the loaded window; counts
	// over the windowed mentions, source-kind distinct, silent on failures
	expect(data.focusEvents).toEqual([
		{ id: 9, title: 'Evento en foco', mentions: 1, sourceKinds: 1 }
	]);
	// the failed followed id degrades; the page event payload survives for the chip
	expect(Object.keys(data.eventsById as Record<string, unknown>)).toEqual(['9']);
	expect(fetchMock.mock.calls.filter(([u]) => String(u).includes('/events/404')).length).toBe(1);
});

it('skips focus rows without in-window mentions and keeps the page alive', async () => {
	stubFetch({
		'/api/stats/overview': { by_source: { news_rss: 4 } },
		'/api/keywords': [],
		'/api/stats/feed': metrics,
		'/api/mentions': { items: [], total: 0 },
		'/api/clients/1/events/8': {
			id: 8, title: 'Solo fuera de ventana', mention_count: 2, source_count: 1, summary: null,
			first_seen_at: '2026-10-01T10:00:00Z', last_seen_at: '2026-10-01T11:00:00Z',
			mentions: [
				{ id: 3, source: 'news_rss', url: 'https://a.example/3', title: 'Antigua', sentiment: null, published_at: '2026-10-01T12:00:00Z' }
			]
		}
	});
	const data = (await load(
		route('http://localhost/feed?since=2026-10-14&until=2026-10-14', {
			mm_prefs: JSON.stringify({ saved: [], follow: [8], seen: {} })
		})
	)) as Record<string, unknown>;
	expect(data.focusEvents).toEqual([]);
	expect(data.mentions).toMatchObject({ items: [], total: 0 });
});
