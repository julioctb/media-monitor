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
		return new Response(JSON.stringify(body ?? null), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

it('keeps every channel pool call within the API limit at deep offsets', async () => {
	const fetchMock = stubFetch({
		'/api/stats/overview': { by_source: { elpopular: 12 } },
		'/api/keywords': [],
		'/api/mentions': { items: [], total: 0 }
	});

	const url = new URL('http://localhost/?channel=news&limit=200&offset=450');
	await load({ url } as never);

	const mentionCalls = fetchMock.mock.calls
		.map((call) => new URL(String(call[0]), 'http://localhost'))
		.filter((u) => u.pathname === '/api/mentions');
	expect(mentionCalls.length).toBeGreaterThan(0);
	for (const callUrl of mentionCalls) {
		const limit = Number(callUrl.searchParams.get('limit'));
		expect(limit).toBeLessThanOrEqual(500);
	}
});
