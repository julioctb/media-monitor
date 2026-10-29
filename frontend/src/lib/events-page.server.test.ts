import { afterEach, expect, it, vi } from 'vitest';

import { load } from '../routes/events/+page.server';

const eventsFixture = [
	{
		id: 9,
		title: 'Evento de prueba',
		mention_count: 1,
		source_count: 1,
		summary: null,
		first_seen_at: '2026-10-27T15:00:00+00:00',
		last_seen_at: '2026-10-27T18:00:00+00:00'
	}
];

/** Loader event stub: url + cookie jar (el lector de mm_prefs). */
function route(url = 'http://localhost/events', jar: Record<string, string> = {}) {
	return {
		url: new URL(url, 'http://localhost'),
		cookies: { get: (name: string) => jar[name] }
	} as never;
}

afterEach(() => {
	vi.unstubAllGlobals();
});

it('loads the full population behind the page cap, without legacy query params', async () => {
	const calls: string[] = [];
	const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
		calls.push(String(input));
		return new Response(JSON.stringify(eventsFixture), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	});
	vi.stubGlobal('fetch', fetchMock);

	// el filtro legacy por query ya no participa: el load ni lo mira
	const data = (await load(route('http://localhost/events?scope=eco'))) as Record<
		string,
		unknown
	>;

	// una sola llamada, cap de la ventana de presentación como único param
	expect(calls).toHaveLength(1);
	const call = new URL(calls[0]!, 'http://localhost');
	expect(call.pathname).toBe('/api/clients/1/events');
	expect([...call.searchParams.keys()]).toEqual(['limit']);
	expect(call.searchParams.get('limit')).toBe('200');

	// forma pública: eventos + prefs; sin clave de scope
	expect(Object.keys(data).sort()).toEqual(['events', 'prefs']);
	expect(data.events).toEqual(eventsFixture);
});
