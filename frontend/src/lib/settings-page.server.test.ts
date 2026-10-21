import { afterEach, expect, it, vi } from 'vitest';

import { actions } from '../routes/settings/+page.server';

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
		client_name: 'acme',
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21', '8', '8', '6']
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as { digest_hours?: number[] };
	expect(body['digest_hours']).toEqual([6, 8, 21]);
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

it('persists the facebook row kind, defaulting absent to page', async () => {
	stubFetch(SETTINGS_ROW);

	const result = await save({
		client_name: 'acme',
		timezone: 'America/Mexico_City',
		retention_days: '30',
		digest_hour: ['21'],
		fb_page_id: ['1090003732034388', '1001'],
		fb_token: ['t1', 't2'],
		fb_label: ['Grupo', ''],
		fb_kind: ['group'] // second row omits the select: legacy/absent == page
	});

	expect(result['ok']).toBe(true);
	const body = savedBodies[0] as { facebook_pages?: Record<string, string>[] };
	expect(body['facebook_pages']).toEqual([
		{ page_id: '1090003732034388', token: 't1', label: 'Grupo', kind: 'group' },
		{ page_id: '1001', token: 't2', label: '', kind: 'page' }
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
