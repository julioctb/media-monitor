import { afterEach, describe, expect, it, vi } from 'vitest';
import {
	ApiError,
	createKeyword,
	deleteKeyword,
	getClientSettings,
	getEvent,
	getEventCoverage,
	getFeedStats,
	listEvents,
	listMentions,
	testAi,
	updateClientSettings
} from './api';

function jsonResponse(status: number, body: unknown): Response {
	return new Response(JSON.stringify(body), {
		status,
		headers: { 'content-type': 'application/json' }
	});
}

function stubFetch(implementation: (url: string, init?: RequestInit) => Promise<Response>) {
	const fetchMock = vi.fn(implementation);
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

afterEach(() => {
	vi.unstubAllGlobals();
});

describe('api client', () => {
	it('encodes Feed scalar filters and repeated sources without pagination', async () => {
		const body = { total: 0, by_source: {}, by_sentiment: { positive: 0, negative: 0, neutral: 0, none: 0 }, news_medium_count: 0, result_group_count: 0 };
		const fetchMock = stubFetch(async () => jsonResponse(200, body));
		// Runtime extra properties must not leak even if a caller passes a list query.
		const query = { source: 'news_rss', sources: ['news_rss', 'gdelt'], sentiment: 'none' as const, keyword_id: 0, classifier: 'political', label: 'political', medium: 'www.alpha.example', q: 'budget & tax %', since: '2026-10-14T00:00:00+06:00', until: '2026-10-15T23:59:59-06:00', limit: 1, offset: 80, sort: 'ignored' };
		expect(await getFeedStats(query, { baseUrl: 'http://fixture.invalid' })).toEqual(body);
		const [url, init] = fetchMock.mock.calls[0];
		const actual = new URL(url);
		expect(actual.pathname).toBe('/api/stats/feed');
		expect(init?.method).toBe('GET');
		expect(actual.searchParams.getAll('sources')).toEqual(['news_rss', 'gdelt']);
		for (const key of ['source', 'sentiment', 'keyword_id', 'classifier', 'label', 'medium', 'q', 'since', 'until'] as const) expect(actual.searchParams.get(key)).toBe(String(query[key]));
		for (const key of ['limit', 'offset', 'sort']) expect(actual.searchParams.has(key)).toBe(false);
	});

	it('omits empty Feed filters and keeps empty sources unrestricted on the wire', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, { total: 0 }));
		await getFeedStats({ q: '', source: '', sources: [] });
		expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/api/stats/feed');
	});

	it('does not convert aggregate errors or missing payloads into measured zeros', async () => {
		const issues = [{ loc: ['query', 'sentiment'], msg: 'invalid tone' }];
		stubFetch(async () => jsonResponse(422, { detail: issues }));
		await expect(getFeedStats()).rejects.toMatchObject({ status: 422, detail: issues, message: 'invalid tone' });
		stubFetch(async () => jsonResponse(200, null));
		expect(await getFeedStats()).toBeNull();
		stubFetch(async () => { throw new Error('offline'); });
		await expect(getFeedStats()).rejects.toMatchObject({ status: 0 });
	});

	it('builds the mentions URL from the non-empty filters only', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, { items: [], total: 0 }));

		const page = await listMentions({
			source: 'gdelt',
			sentiment: 'none',
			q: 'nvidia',
			limit: 25,
			offset: 50
		});

		expect(page).toEqual({ items: [], total: 0 });
		expect(fetchMock).toHaveBeenCalledTimes(1);
		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe(
			'http://localhost:8000/api/mentions?source=gdelt&sentiment=none&q=nvidia&limit=25&offset=50'
		);
		expect(init?.method).toBe('GET');
	});

	it('omits absent filters and keeps keyword_id zero safe', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, { items: [], total: 0 }));

		await listMentions({ keyword_id: 0 });

		const [url] = fetchMock.mock.calls[0] as unknown as [string];
		expect(url).toBe('http://localhost:8000/api/mentions?keyword_id=0');
	});

	it('percent-encodes text search values', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, { items: [], total: 0 }));

		await listMentions({ q: 'media & tech' });

		const [url] = fetchMock.mock.calls[0] as unknown as [string];
		expect(new URL(url).searchParams.get('q')).toBe('media & tech');
	});

	it('posts JSON bodies with the JSON content type', async () => {
		const fetchMock = stubFetch(async () =>
			jsonResponse(201, { id: 1, text: 'nvidia', language: 'es', is_active: true, created_at: 'now' })
		);

		const keyword = await createKeyword({ text: 'nvidia', language: 'es' });

		expect(keyword.text).toBe('nvidia');
		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('http://localhost:8000/api/keywords');
		expect(init.method).toBe('POST');
		expect(init.headers).toMatchObject({ 'content-type': 'application/json' });
		expect(JSON.parse(String(init.body))).toEqual({ text: 'nvidia', language: 'es' });
	});

	it('surfaces the API detail message on error responses', async () => {
		stubFetch(async () => jsonResponse(409, { detail: "keyword 'nvidia' already exists" }));

		const error = await createKeyword({ text: 'nvidia', language: 'es' }).then(
			() => null,
			(e: unknown) => e as ApiError
		);

		expect(error).toBeInstanceOf(ApiError);
		expect(error?.status).toBe(409);
		expect(error?.message).toContain('already exists');
	});

	it('summarizes 422 validation issues', async () => {
		stubFetch(async () =>
			jsonResponse(422, { detail: [{ loc: ['body', 'text'], msg: 'text must not be empty' }] })
		);

		const error = await createKeyword({ text: '  ', language: 'es' }).then(
			() => null,
			(e: unknown) => e as ApiError
		);

		expect(error?.status).toBe(422);
		expect(error?.message).toContain('text must not be empty');
	});

	it('falls back to a generic message for non-JSON errors', async () => {
		stubFetch(async () => new Response('oops', { status: 500 }));

		const error = await listMentions().then(
			() => null,
			(e: unknown) => e as ApiError
		);

		expect(error?.status).toBe(500);
		expect(error?.message).toContain('500');
	});

	it('returns void on 204 and sends DELETE', async () => {
		const fetchMock = stubFetch(async () => new Response(null, { status: 204 }));

		await expect(deleteKeyword(7)).resolves.toBeUndefined();

		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('http://localhost:8000/api/keywords/7');
		expect(init?.method).toBe('DELETE');
	});

	it('wraps connection failures as ApiError with status 0', async () => {
		stubFetch(async () => {
			throw new Error('connection refused');
		});

		const error = await listMentions().then(
			() => null,
			(e: unknown) => e as ApiError
		);

		expect(error).toBeInstanceOf(ApiError);
		expect(error?.status).toBe(0);
		expect(error?.message).toContain('connection refused');
	});

	it('honors a per-call base URL override without double slashes', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, { items: [], total: 0 }));

		await listMentions({}, { baseUrl: 'http://api:8000/' });

		const [url] = fetchMock.mock.calls[0] as unknown as [string];
		expect(url).toBe('http://api:8000/api/mentions');
	});

	it('GETs the client settings row', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, { id: 1, client_name: 'Grupo' }));

		const settings = await getClientSettings();

		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('http://localhost:8000/api/settings');
		expect(init?.method).toBe('GET');
		expect(settings).toEqual({ id: 1, client_name: 'Grupo' });
	});

	it('PUTs the settings payload to /api/settings', async () => {
		const savedRow = {
			id: 1,
			client_id: 1,
			client_name: 'Grupo Julio',
			timezone: 'America/Monterrey',
			retention_days: 30,
			gdelt_enabled: false,
			facebook_pages: [],
			rss_feeds: ['https://ejemplo.com/feed.xml'],
			ai_provider: 'openai',
			ai_api_key: 'sk-test',
			ai_base_url: 'https://api.openai.com/v1',
			ai_model: 'gpt-4o-mini',
			updated_at: '2026-10-09T00:00:00Z'
		};
		const fetchMock = stubFetch(async () => jsonResponse(200, savedRow));

		const saved = await updateClientSettings({
			client_name: 'Grupo Julio',
			timezone: 'America/Monterrey',
			retention_days: 30,
			gdelt_enabled: false,
			facebook_pages: [],
			rss_feeds: ['https://ejemplo.com/feed.xml'],
			ai_provider: 'openai',
			ai_api_key: 'sk-test',
			ai_base_url: 'https://api.openai.com/v1',
			ai_model: 'gpt-4o-mini'
		});

		expect(saved).toEqual(savedRow);
		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('http://localhost:8000/api/settings');
		expect(init?.method).toBe('PUT');
		expect(init?.headers).toMatchObject({ 'content-type': 'application/json' });
		expect(JSON.parse(String(init?.body))).toEqual({
			client_name: 'Grupo Julio',
			timezone: 'America/Monterrey',
			retention_days: 30,
			gdelt_enabled: false,
			facebook_pages: [],
			rss_feeds: ['https://ejemplo.com/feed.xml'],
			ai_provider: 'openai',
			ai_api_key: 'sk-test',
			ai_base_url: 'https://api.openai.com/v1',
			ai_model: 'gpt-4o-mini'
		});
	});

	it('probes the ai provider with the selected engine', async () => {
		const fetchMock = stubFetch(async () =>
			jsonResponse(200, {
				ok: false,
				engine: 'openai',
				model: 'gpt-4o-mini',
				latency_ms: null,
				label: null,
				error: 'api_key is required for the openai provider'
			})
		);

		const probe = await testAi({ provider: 'openai', api_key: null, model: 'gpt-4o-mini' });

		expect(probe.ok).toBe(false);
		expect(probe.error).toContain('api_key is required');
		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('http://localhost:8000/api/settings/test-ai');
		expect(init?.method).toBe('POST');
		expect(JSON.parse(String(init?.body))).toEqual({
			provider: 'openai',
			api_key: null,
			model: 'gpt-4o-mini'
		});
	});

	it('lists canonical events under the tenant scope', async () => {
		const fetchMock = stubFetch(async () => jsonResponse(200, []));

		const events = await listEvents({ limit: 100 });

		expect(events).toEqual([]);
		const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
		expect(url).toBe('http://localhost:8000/api/clients/1/events?limit=100');
		expect(init?.method).toBe('GET');
	});

	it('fetches one event and its coverage by id', async () => {
		const fetchMock = stubFetch(async () =>
			jsonResponse(200, { id: 9, title: 'x', mentions: [], by_source: [] })
		);

		const detail = await getEvent(9);
		const coverage = await getEventCoverage(9, { baseUrl: 'http://api:8000' });

		expect((detail as { id: number }).id).toBe(9);
		expect((coverage as { by_source: unknown[] }).by_source).toEqual([]);
		const urls = fetchMock.mock.calls.map((call) => call[0]);
		expect(urls).toContain('http://localhost:8000/api/clients/1/events/9');
		expect(urls).toContain('http://api:8000/api/clients/1/events/9/coverage');
	});
});
