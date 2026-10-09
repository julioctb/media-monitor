import { afterEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createKeyword, deleteKeyword, listMentions } from './api';

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
});
