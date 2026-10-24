import { afterEach, expect, it, vi } from 'vitest';

import { actions } from '../routes/settings/+page.server';
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
		enrich_max_per_cycle: '40',
		fetch_max_per_cycle: '120'
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as Record<string, unknown>;
	expect(body['digest_focus_person_id']).toBe(7);
	expect(body['enrich_max_per_cycle']).toBe(40);
	expect(body['fetch_max_per_cycle']).toBe(120);
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
