import { afterEach, expect, it, vi } from 'vitest';

import { actions, load } from '../routes/settings/+page.server';
import { normalizeFacebookPageRef } from '$lib/facebook-page';

/**
 * Settings save (digest-multi-cut): the digest-hours chips serialize to a
 * deduped, sorted `digest_hours` array on the PUT; invalid sets fail with
 * 400 and a friendly message instead of reaching the API.
 */

const savedBodies: unknown[] = [];

function stubFetch(row: object) {
	const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const path = new URL(String(input), 'http://localhost').pathname;
		if (path === '/api/settings' && init?.method === 'PUT') {
			savedBodies.push(JSON.parse(String(init.body)));
			return new Response(JSON.stringify(row), {
				status: 200,
				headers: { 'content-type': 'application/json' }
			});
		}
		return new Response(JSON.stringify(row), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	});
	vi.stubGlobal('fetch', fetchMock);
	return fetchMock;
}

afterEach(() => {
	savedBodies.length = 0;
	vi.unstubAllGlobals();
});

const SETTINGS_ROW = {
	id: 1,
	client_id: 1,
	client_name: 'acme',
	timezone: 'America/Mexico_City',
	retention_days: 30,
	digest_hour: 21,
	digest_hours: [21],
	digest_focus_person_id: 7,
	enrich_max_per_cycle: 40,
	fetch_max_per_cycle: 120,
	gdelt_enabled: true,
	facebook_pages: [],
	rss_feeds: [],
	scrapers: [],
	ai_provider: 'local',
	ai_api_key: null,
	ai_base_url: null,
	ai_model: null,
	ai_model_fast: null,
	updated_at: '2026-10-19T03:00:00Z'
};

function formRequest(entries: Record<string, string | string[]>): Request {
	const form = new FormData();
	for (const [key, value] of Object.entries(entries)) {
		for (const entry of Array.isArray(value) ? value : [value]) {
			form.append(key, entry);
		}
	}
	return new Request('http://localhost/settings', { method: 'POST', body: form });
}

const saveForm = formRequest;

async function save(entries: Record<string, string | string[]>) {
	// ActionFailure carries {status, data}; success returns the plain result.
	return actions.save({ request: saveForm(entries) } as never) as Promise<{
		status?: number;
		data?: Record<string, unknown>;
		ok?: boolean;
	}>;
}

function failureOf(result: { status?: number; data?: Record<string, unknown> }) {
	return { status: result.status ?? -1, data: result.data ?? {} };
}

it('redacts reviewer credentials from load props while preserving the watchlist guard', async () => {
	const row = { ...SETTINGS_ROW, watchlist: null,
		digest_reviewer_provider: 'openai', digest_reviewer_api_key: 'fixture-only-loaded-secret',
		digest_reviewer_api_key_set: true };
	vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) =>
		new Response(JSON.stringify(new URL(String(input)).pathname === '/api/settings' ? row : []),
			{ headers: { 'content-type': 'application/json' } })));
	const data = await load({} as never) as { settings: Record<string, unknown> };
	expect(data.settings.digest_reviewer_api_key).toBe('');
	expect(data.settings.digest_reviewer_api_key_set).toBe(true);
	expect(data.settings.watchlist).toEqual([]);
	expect(JSON.stringify(data)).not.toContain('fixture-only-loaded-secret');
});

it('serializes digest hours as a deduped sorted array', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await save({
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21', '8', '8', '6'],
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120'
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as { digest_hours?: number[] };
	expect(body['digest_hours']).toEqual([6, 8, 21]);
});

it('persists focus person and per-cycle caps on the save PUT', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await save({
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21'],
		digest_focus_person_id: '7',
		watchlist: ['3', '5', '3'],
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120'
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as Record<string, unknown>;
	expect(body['digest_focus_person_id']).toBe(7);
	// F7: watchlist dedupes to positive ints on the wire.
	expect(body['watchlist']).toEqual([3, 5]);
	expect(body['enrich_max_per_cycle']).toBe(40);
	expect(body['fetch_max_per_cycle']).toBe(120);
});

it('persists an empty watchlist when no person is checked', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await save({
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21'],
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120'
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as Record<string, unknown>;
	expect(body['watchlist']).toEqual([]);
});

it('clears the focus person when the select is empty', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await save({
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21'],
		digest_focus_person_id: '',
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120'
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as Record<string, unknown>;
	expect(body['digest_focus_person_id']).toBeNull();
});

it('fails with 400 on out-of-range cycle caps', async () => {
	stubFetch(SETTINGS_ROW);

	const result = failureOf(
		await save({
			timezone: 'America/Mexico_City',
			retention_days: '30',
			digest_hour: ['21'],
			enrich_max_per_cycle: '0',
			fetch_max_per_cycle: '1001'
		})
	);

	expect(result.status).toBe(400);
});

it('fails with 400 when no valid hour is set', async () => {
	stubFetch(SETTINGS_ROW);

	const result = failureOf(
		await save({
			retention_days: '30',
			digest_hour: ['abc', '99']
		})
	);

	expect(result.status).toBe(400);
	expect(result.data['ok']).toBe(false);
	expect(savedBodies).toHaveLength(0); // never reached the API
});

it('fails with 400 above the 8-cut cap', async () => {
	stubFetch(SETTINGS_ROW);

	const result = failureOf(
		await save({
			retention_days: '30',
			digest_hour: ['0', '1', '2', '3', '4', '5', '6', '7', '8']
		})
	);

	expect(result.status).toBe(400);
});

it('persists facebook rows from urls, normalized tokenless', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await save({
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21'],
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120',
		facebook_pages: JSON.stringify([
			{ page_id: 'facebook.com/105335348671635', label: 'Despierta BUAP' },
			{ page_id: '', label: 'Vacía' }
		])
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as { facebook_pages?: Record<string, string>[] };
	expect(body['facebook_pages']).toEqual([{ page_id: '105335348671635', label: 'Despierta BUAP' }]);
});

it('dedupes facebook refs keeping the first label, dropping invalid rows', async () => {
	stubFetch(SETTINGS_ROW);

	await save({
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21'],
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120',
		facebook_pages: JSON.stringify([
			{ page_id: 'facebook.com/econsulta', label: 'Primera' },
			{ page_id: 'https://www.facebook.com/econsulta?sk=wall', label: 'Segunda' }, // same ref: dropped
			{ page_id: 'https://ejemplo.com/nope', label: 'Otro' }, // foreign domain: dropped
			{ page_id: 'https://www.facebook.com/profile.php?id=987', label: 'Perfil' }
		])
	});

	const body = savedBodies[0] as { facebook_pages?: Record<string, string>[] };
	expect(body['facebook_pages']).toEqual([
		{ page_id: 'econsulta', label: 'Primera' },
		{ page_id: '987', label: 'Perfil' }
	]);
});

// -- Keyword actions served by the settings page (embedded panel) --

const KEYWORD_ROW = {
	id: 7,
	text: 'BUAP',
	language: 'es',
	is_active: true,
	created_at: '2026-10-20T00:00:00Z'
};

interface RecordedCall {
	path: string;
	method: string;
	body?: unknown;
}

/** Stub fetch recording every call; replies KEYWORD_ROW for keyword routes. */
function stubKeywordFetch() {
	const calls: RecordedCall[] = [];
	const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
		const url = new URL(String(input));
		const method = init?.method ?? 'GET';
		const call: RecordedCall = { path: url.pathname, method };
		if (init?.body) call.body = JSON.parse(String(init.body));
		calls.push(call);
		return new Response(JSON.stringify(KEYWORD_ROW), {
			status: 200,
			headers: { 'content-type': 'application/json' }
		});
	});
	vi.stubGlobal('fetch', fetchMock);
	return calls;
}

async function runAction(
	name: 'create' | 'toggle' | 'delete',
	entries: Record<string, string | string[]>
) {
	return actions[name]({ request: formRequest(entries) } as never) as Promise<{
		status?: number;
		data?: Record<string, unknown>;
		ok?: boolean;
		message?: string;
	}>;
}

it('creates a keyword through the page action', async () => {
	const calls = stubKeywordFetch();

	const result = await runAction('create', { text: 'BUAP', language: 'es' });

	expect(result.ok).toBe(true);
	const post = calls.find((call) => call.path === '/api/keywords' && call.method === 'POST');
	expect(post?.body).toMatchObject({ text: 'BUAP', language: 'es' });
});

it('fails keyword create with 400 on blank text', async () => {
	const calls = stubKeywordFetch();

	const result = await runAction('create', { text: '   ' });

	const failure = { status: result.status ?? -1, data: result.data ?? {} };
	expect(failure.status).toBe(400);
	expect(failure.data.ok).toBe(false);
	expect(calls).toHaveLength(0); // never reached the API
});

it('toggles a keyword through the page action', async () => {
	const calls = stubKeywordFetch();

	const result = await runAction('toggle', { id: '7', is_active: '0' });

	expect(result.ok).toBe(true);
	const patch = calls.find((call) => call.path === '/api/keywords/7' && call.method === 'PATCH');
	expect(patch?.body).toEqual({ is_active: false });
});

it('deletes a keyword through the page action', async () => {
	const calls = stubKeywordFetch();

	const result = await runAction('delete', { id: '7' });

	expect(result.ok).toBe(true);
	expect(calls).toContainEqual({ path: '/api/keywords/7', method: 'DELETE' });
});

// -- Facebook page-ref normalizer (tokenless source entry) --

it('normalizes a full page url to its slug', () => {
	expect(normalizeFacebookPageRef('https://www.facebook.com/econsulta')).toBe('econsulta');
});

it('strips permalink paths and querystrings down to the slug', () => {
	expect(normalizeFacebookPageRef('facebook.com/econsulta/posts/123?ref=page')).toBe('econsulta');
});

it('resolves profile.php to the numeric id', () => {
	expect(normalizeFacebookPageRef('https://www.facebook.com/profile.php?id=987')).toBe('987');
});

it('keeps group refs intact', () => {
	expect(normalizeFacebookPageRef('https://www.facebook.com/groups/555/')).toBe('groups/555');
});

it('passes bare slugs and numeric ids through', () => {
	expect(normalizeFacebookPageRef('econsulta')).toBe('econsulta');
	expect(normalizeFacebookPageRef(' 105335348671635 ')).toBe('105335348671635');
});

it('rejects foreign domains and empty input', () => {
	expect(normalizeFacebookPageRef('https://ejemplo.com/econsulta')).toBeNull();
	expect(normalizeFacebookPageRef('')).toBeNull();
	expect(normalizeFacebookPageRef('   ')).toBeNull();
});

it('saves only the four independent reviewer fields without dispatching a probe', async () => {
	const fetchMock = stubFetch(SETTINGS_ROW);
	const action = actions['save-reviewer'];
	expect(action).toBeTypeOf('function');
	const result = await action({ request: formRequest({
		digest_reviewer_provider: 'openai',
		digest_reviewer_base_url: ' https://reviewer.invalid/v1 ',
		digest_reviewer_model: ' fixture-reviewer ',
		digest_reviewer_api_key: ' fixture-only-new-key ',
		ai_provider: 'openai', ai_model: 'must-not-change', ai_api_key: 'must-not-change',
		watchlist: ['999'], retention_days: '1', digest_reviewer_revision: 'must-not-travel'
	}) } as never);
	expect(result).toMatchObject({ action: 'save-reviewer', ok: true });
	expect(savedBodies).toEqual([{
		digest_reviewer_provider: 'openai', digest_reviewer_base_url: 'https://reviewer.invalid/v1',
		digest_reviewer_model: 'fixture-reviewer', digest_reviewer_api_key: 'fixture-only-new-key'
	}]);
	expect(fetchMock).toHaveBeenCalledTimes(1);
	expect(JSON.stringify(result)).not.toContain('fixture-only-new-key');
});

it.each(['', 'local', 'hybrid'])('rejects reviewer mode %j before any API request', async (provider) => {
	const fetchMock = stubFetch(SETTINGS_ROW);
	const result = await actions['save-reviewer']({ request: formRequest({
		digest_reviewer_provider: provider, digest_reviewer_api_key: 'fixture-only-invalid-key'
	}) } as never);
	expect(result).toMatchObject({ status: 400, data: { action: 'save-reviewer', ok: false } });
	expect(fetchMock).not.toHaveBeenCalled();
	expect(JSON.stringify(result)).not.toContain('fixture-only-invalid-key');
});

it.each([422, 503, 0])('returns a secret-safe reviewer failure for API status %i', async (status) => {
	const secret = 'fixture-only-echoed-key';
	vi.stubGlobal('fetch', vi.fn(async () => {
		if (status === 0) throw new Error(`offline ${secret}`);
		return new Response(JSON.stringify({ detail: [{ msg: `invalid ${secret}`, input: secret }] }),
			{ status, headers: { 'content-type': 'application/json' } });
	}));
	const outcome = actions['save-reviewer']({ request: formRequest({
		digest_reviewer_provider: 'openai', digest_reviewer_api_key: secret
	}) } as never);
	await expect(outcome).resolves.toMatchObject({ status: status || 502, data: {
		action: 'save-reviewer', ok: false,
		message: 'No se pudo guardar el revisor. Revisa el modo, la URL y el modelo.'
	} });
	expect(JSON.stringify(await outcome)).not.toContain(secret);
});

it.each([undefined, '', '   '])('preserves the reviewer blank-key sentinel %j', async (key) => {
	stubFetch(SETTINGS_ROW);
	await actions['save-reviewer']({ request: formRequest({ digest_reviewer_provider: 'inherit',
		...(key === undefined ? {} : { digest_reviewer_api_key: key }) }) } as never);
	expect(savedBodies).toEqual([{ digest_reviewer_provider: 'inherit',
		digest_reviewer_base_url: null, digest_reviewer_model: null, digest_reviewer_api_key: '' }]);
});

// -- X source mode (free/paid) and its masked API key --

/**
 * The dedicated X action must PUT a PARTIAL body: only x_mode and
 * x_api_key. '' travels explicitly — the API reads it as "keep the
 * stored key" (masked-GET semantics: the UI never holds the value).
 */
async function runXAction(entries: Record<string, string>) {
	return actions['save-x']({ request: formRequest(entries) } as never) as Promise<{
		status?: number;
		data?: Record<string, unknown>;
		ok?: boolean;
	}>;
}

it('saves x mode and key as a partial payload', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await runXAction({ x_mode: 'paid', x_api_key: ' tok-123 ' });

	expect(result['ok']).toBe(true);
	expect(savedBodies[0]).toEqual({ x_mode: 'paid', x_api_key: 'tok-123' });
});

it('sends an empty key so the stored one is kept', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await runXAction({ x_mode: 'free' });

	expect(result['ok']).toBe(true);
	expect(savedBodies[0]).toEqual({ x_mode: 'free', x_api_key: '' });
});

it('rejects an unknown x mode with 400 before the API', async () => {
	stubFetch(SETTINGS_ROW);

	const result = failureOf(await runXAction({ x_mode: 'hybrid', x_api_key: 'k' }));

	expect(result.status).toBe(400);
	expect(result.data['ok']).toBe(false);
	expect(savedBodies).toHaveLength(0);
});
