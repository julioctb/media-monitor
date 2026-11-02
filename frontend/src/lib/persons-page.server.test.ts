import { afterEach, expect, it, vi } from 'vitest';
import { load } from '../routes/persons/+page.server';
import { listPersons } from '$lib/api';

vi.mock('$lib/api', async (original) => ({
	...(await original<typeof import('$lib/api')>()), listPersons: vi.fn()
}));

afterEach(() => vi.clearAllMocks());

it('keeps one bounded 200-person pool and cookie preferences regardless of directory page params', async () => {
	const persons = [{ id: 7, name: 'Ana', sources: ['news_rss', 'x_twitter'] }];
	vi.mocked(listPersons).mockResolvedValue(persons as never);
	const getCookie = vi.fn(() => JSON.stringify({ saved: [4], follow: [8], persons: [7], seen: { '8': 'marker' } }));
	const result = await load({
		url: new URL('http://localhost/persons?q=%20Ana%20&sort=recent&page=8&offset=175'),
		cookies: { get: getCookie }
	} as never);
	expect(listPersons).toHaveBeenCalledExactlyOnceWith({ sort: 'mentions', q: 'Ana', limit: 200 });
	expect(getCookie).toHaveBeenCalledWith('mm_prefs');
	expect(result).toEqual({ persons, q: 'Ana', prefs: { saved: [4], follow: [8], persons: [7], seen: { '8': 'marker' } } });
});

it('keeps blank search unrestricted and old preference cookies compatible', async () => {
	vi.mocked(listPersons).mockResolvedValue([]);
	const result = await load({ url: new URL('http://localhost/persons?q=%20'), cookies: { get: () => undefined } } as never);
	expect(listPersons).toHaveBeenCalledWith({ sort: 'mentions', q: undefined, limit: 200 });
	expect(result).toEqual({ persons: [], q: '', prefs: { saved: [], follow: [], persons: [], seen: {} } });
});
