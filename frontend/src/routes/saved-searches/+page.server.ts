import { error, fail } from '@sveltejs/kit';
import {
	ApiError,
	createSavedSearch,
	deleteSavedSearch,
	listSavedSearches,
	updateSavedSearch
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const SOURCES = ['news_rss', 'gdelt', 'x_twitter', 'facebook_page', 'rss_custom'] as const;
const MAX_NAME = 200;
const MAX_QUERY = 500;

interface SavedSearchActionResult {
	action: 'create' | 'toggle' | 'delete';
	ok: boolean;
	message: string;
	name: string;
}

function failure(action: SavedSearchActionResult['action'], status: number, message: string, name = '') {
	return fail(status, { action, ok: false, message, name } satisfies SavedSearchActionResult);
}

function apiFailure(action: SavedSearchActionResult['action'], cause: unknown, name = '') {
	const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 502;
	const message = cause instanceof Error ? cause.message : 'unknown error';
	return failure(action, status, message, name);
}

export const load: PageServerLoad = async () => {
	try {
		return { savedSearches: await listSavedSearches(), sources: SOURCES };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'unknown error';
		throw error(status, `Could not load saved searches: ${detail}`);
	}
};

export const actions: Actions = {
	create: async ({ request }) => {
		const form = await request.formData();
		const name = String(form.get('name') ?? '').trim();
		const query = String(form.get('query') ?? '').trim();
		const sources = SOURCES.filter((source) => form.get(`src_${source}`) === '1');
		const classifier = String(form.get('classifier') ?? '').trim();
		const label = String(form.get('label') ?? '').trim();
		const rangeDaysRaw = String(form.get('range_days') ?? '7');
		const range_days = /^\d+$/.test(rangeDaysRaw) ? Number(rangeDaysRaw) : 7;

		if (!name) return failure('create', 400, 'A name is required.');
		if (name.length > MAX_NAME)
			return failure('create', 400, `Name is limited to ${MAX_NAME} characters.`, name);
		if (!query) return failure('create', 400, 'A query is required.', name);
		if (query.length > MAX_QUERY)
			return failure('create', 400, `Query is limited to ${MAX_QUERY} characters.`, name);
		if (range_days < 1 || range_days > 365)
			return failure('create', 400, 'Range must be between 1 and 365 days.', name);

		try {
			const saved = await createSavedSearch({
				name,
				query,
				sources: [...sources],
				classifier: classifier || null,
				label: label || null,
				range_days
			});
			return {
				action: 'create',
				ok: true,
				message: `Saved search “${saved.name}” created.`,
				name: ''
			} satisfies SavedSearchActionResult;
		} catch (cause) {
			return apiFailure('create', cause, name);
		}
	},

	toggle: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const isActive = String(form.get('is_active')) === '1';

		if (!Number.isInteger(id) || id <= 0) {
			return failure('toggle', 400, 'Invalid identifier.');
		}

		try {
			await updateSavedSearch(id, { is_active: isActive });
			return {
				action: 'toggle',
				ok: true,
				message: isActive ? 'Saved search activated.' : 'Saved search paused.',
				name: ''
			} satisfies SavedSearchActionResult;
		} catch (cause) {
			return apiFailure('toggle', cause);
		}
	},

	delete: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));

		if (!Number.isInteger(id) || id <= 0) {
			return failure('delete', 400, 'Invalid identifier.');
		}

		try {
			await deleteSavedSearch(id);
			return { action: 'delete', ok: true, message: 'Saved search deleted.', name: '' };
		} catch (cause) {
			return apiFailure('delete', cause);
		}
	}
};
