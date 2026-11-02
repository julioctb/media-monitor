import { afterEach, expect, it, vi } from 'vitest';

import { GET } from '../routes/api/persons/[id]/+server';

afterEach(() => vi.unstubAllGlobals());

function event(id: string, query = '') {
	return {
		params: { id },
		url: new URL(`http://localhost/api/persons/${id}${query}`)
	} as never;
}

it('proxies bounded timeline pagination through the same-origin server endpoint', async () => {
	const fetchMock = vi.fn(async (_input: RequestInfo | URL) =>
		new Response(JSON.stringify({ id: 7, name: 'Lilia Cedillo', timeline: [] }), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		})
	);
	vi.stubGlobal('fetch', fetchMock);

	const response = await GET(event('7', '?limit=10&offset=20&order=oldest'));
	expect(response.status).toBe(200);
	const upstream = new URL(String(fetchMock.mock.calls[0]?.[0]), 'http://localhost');
	expect(upstream.pathname).toBe('/api/clients/1/persons/7');
	expect(Object.fromEntries(upstream.searchParams)).toEqual({ limit: '10', offset: '20', order: 'oldest' });
});

it('turns an unreachable backend into a valid same-origin unavailable response', async () => {
	vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('offline fixture'); }));
	const response = await GET(event('7'));
	expect(response.status).toBe(503);
	expect(await response.json()).toEqual({ message: 'No se pudo cargar la persona' });
});

it('rejects invalid person ids without requesting the backend', async () => {
	const fetchMock = vi.fn();
	vi.stubGlobal('fetch', fetchMock);
	const response = await GET(event('invalid'));
	expect(response.status).toBe(404);
	expect(fetchMock).not.toHaveBeenCalled();
});
