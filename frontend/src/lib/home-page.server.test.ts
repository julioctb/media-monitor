import { afterEach, expect, it, vi } from 'vitest';

import { load } from '../routes/+page.server';

/**
 * Home legend (digest-multi-cut): with no summary for the requested day the
 * load must answer summary:null plus `latest_updated_at` from the newest
 * stored day — the fallback that swapped in the previous digest is gone.
 * The v2 load also carries the /stats/day aggregates, the negative-events
 * scan and the «ver mes anterior» history window (?before=YYYY-MM-01).
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
const OLDER_A = '2026-09-18';
const OLDER_B = '2026-08-05';
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
		facebook_pages: [{ page_id: '1', label: 'BUAPoficial' }],
		rss_feeds: ['https://a/feed'],
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

function dayStats() {
	const bucket = { positive: 1, negative: 0, neutral: 0, unclassified: 0, total: 1 };
	return {
		date: TODAY,
		timezone: 'America/Mexico_City',
		tones: { media: bucket, social: bucket, field: bucket },
		keywords: [{ id: 7, text: 'BUAP', count: 3 }]
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
function sideRoutes(overrides: RouteTable = {}): RouteTable {
	return {
		'/api/mentions': {
			items: [
				{
					event_id: 33,
					title: 'Nota negativa',
					sentiment: 'negative',
					source: 'news_rss',
					published_at: '2026-10-19T10:00:00Z'
				}
			],
			total: 1
		},
		'/api/clients/1/persons': [],
		'/api/keywords': [{ id: 7, text: 'BUAP', is_active: true }],
		'/api/stats/day': dayStats(),
		...overrides
	};
}

function historyDays(): unknown[] {
	return [
		{ summary_date: TODAY, mode: 'heuristic' },
		{ summary_date: PREV, mode: 'llm' },
		{ summary_date: OLDER_A, mode: 'llm' },
		{ summary_date: OLDER_B, mode: 'heuristic' }
	];
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
		'/api/clients/1/summaries': historyDays(),
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

it('exposes the v2 aggregates: tones, keyword counts and negative events', async () => {
	stubFetch({
		'/api/settings': settingsRow(),
		'/api/clients/1/summaries': historyDays(),
		[`/api/clients/1/summaries/${TODAY}`]: summaryRow(TODAY, UPDATED_ISO),
		...sideRoutes()
	});

	const data = await loadHome();

	// Tone buckets ride /stats/day (media/social/field), not the mention page.
	const tones = data['tones'] as { media: unknown; social: unknown; field: unknown };
	expect(tones).toHaveProperty('field');
	// Active keywords crossed with the day counts stay available to the UI.
	expect(data['keywordCounts']).toEqual([{ id: 7, text: 'BUAP', count: 3 }]);
	// The single negative mention is a majority-negative event.
	expect(data['negativeEvents']).toEqual([
		{
			event_id: 33,
			title: 'Nota negativa',
			source: 'news_rss',
			published_at: '2026-10-19T10:00:00Z'
		}
	]);
	// Ingest sources: google_news + x_index + gdelt + 1 rss feed + 1 fb page.
	expect(data['sourcesCount']).toBe(5);
	// Facebook label for the redes block: plain, never page names.
	expect(data['socialLabels']).toEqual({ facebook_page: 'Facebook' });
});

it('filters the history with ?before and anchors the previous month', async () => {
	stubFetch({
		'/api/settings': settingsRow(),
		'/api/clients/1/summaries': historyDays(),
		[`/api/clients/1/summaries/${TODAY}`]: summaryRow(TODAY, UPDATED_ISO),
		...sideRoutes()
	});

	const paged = await loadHome('?before=2026-10-01');
	// Only the months before October remain visible…
	expect((paged['days'] as { summary_date: string }[]).map((d) => d.summary_date)).toEqual([
		OLDER_A,
		OLDER_B
	]);
	// …and the next anchor is the first day of the newest visible month.
	expect(paged['olderBefore']).toBe('2026-09-01');

	const unfiltered = await loadHome();
	// Full view: the link points at the current-month edge (older months exist).
	expect(unfiltered['olderBefore']).toBe('2026-10-01');
});

it('hides the month link when no older month exists', async () => {
	stubFetch({
		'/api/settings': settingsRow(),
		'/api/clients/1/summaries': [
			{ summary_date: TODAY, mode: 'heuristic' },
			{ summary_date: PREV, mode: 'llm' }
		],
		[`/api/clients/1/summaries/${TODAY}`]: summaryRow(TODAY, UPDATED_ISO),
		...sideRoutes()
	});

	const data = await loadHome();

	expect(data['olderBefore']).toBeNull();
});
