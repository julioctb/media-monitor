import { afterEach, expect, it, vi } from 'vitest';

import { load } from '../routes/+page.server';

/**
 * Home legend (digest-multi-cut): with no summary for the requested day the
 * load must answer summary:null plus `latest_updated_at` from the newest
 * stored day — the fallback that swapped in the previous digest is gone.
 */

type RouteTable = Record<string, unknown>;

function todayInMexicoCity(): string {
	// Same shape as the load's todayIn: calendar date in the client tz.
	return new Intl.DateTimeFormat('en-CA', {
		timeZone: 'America/Mexico_City',
		year: 'numeric',
		month: '2-digit',
		day: '2-digit'
	}).format(new Date());
}

const TODAY = todayInMexicoCity();
const PREV = '2026-10-19';
const UPDATED_ISO = '2026-10-19T21:05:00Z';

function settingsRow() {
	return {
		id: 1,
		client_id: 1,
		client_name: 'acme',
		timezone: 'America/Mexico_City',
		retention_days: 30,
		digest_hour: 21,
		digest_hours: [21],
		gdelt_enabled: true,
		facebook_pages: [],
		rss_feeds: [],
		scrapers: [],
		ai_provider: 'local',
		ai_api_key: null,
		ai_base_url: null,
		ai_model: null,
		updated_at: '2026-10-19T03:00:00Z'
	};
}

function summaryRow(day: string, updated: string) {
	return {
		id: 1,
		client_id: 1,
		summary_date: day,
		content: {},
		narrative: 'n',
		mode: 'heuristic',
		created_at: updated,
		updated_at: updated
	};
}

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

function loadHome(query = '') {
	const url = new URL(`http://localhost/${query}`);
	return load({ url } as never) as Promise<Record<string, unknown>>;
}

/** Side-data endpoints; shapes only need the fields the load reads. */
function sideRoutes(): RouteTable {
	return {
		'/api/mentions': { items: [], total: 0 },
		'/api/persons': [],
		'/api/keywords': []
	};
}

it('answers summary null + latest_updated_at when today has no digest', async () => {
	stubFetch({
		'/api/settings': settingsRow(),
		'/api/clients/1/summaries': [{ summary_date: PREV, mode: 'heuristic' }],
		[`/api/clients/1/summaries/${TODAY}`]: null,
		[`/api/clients/1/summaries/${PREV}`]: summaryRow(PREV, UPDATED_ISO),
		...sideRoutes()
	});

	const data = await loadHome();

	// The previous digest is no longer swapped in: the legend shows instead.
	expect(data['summary']).toBeNull();
	expect(data['latest_updated_at']).toBe(UPDATED_ISO);
	expect(data['days']).toHaveLength(1);
});

it('answers latest_updated_at null when there is no stored day at all', async () => {
	stubFetch({
		'/api/settings': settingsRow(),
		'/api/clients/1/summaries': [],
		[`/api/clients/1/summaries/${TODAY}`]: null,
		...sideRoutes()
	});

	const data = await loadHome();

	expect(data['summary']).toBeNull();
	expect(data['latest_updated_at']).toBeNull();
});

it('keeps the day summary and skips the latest lookup when it exists', async () => {
	const fetchMock = stubFetch({
		'/api/settings': settingsRow(),
		'/api/clients/1/summaries': [{ summary_date: PREV, mode: 'heuristic' }],
		[`/api/clients/1/summaries/${TODAY}`]: summaryRow(TODAY, UPDATED_ISO),
		...sideRoutes()
	});

	const data = await loadHome();

	expect((data['summary'] as { summary_date: string })['summary_date']).toBe(TODAY);
	expect(data['latest_updated_at']).toBeNull();
	const summaryCalls = fetchMock.mock.calls.filter((call) =>
		String(call[0]).includes('/summaries')
	);
	expect(summaryCalls).toHaveLength(2); // day list + today, no extra fetch
});
