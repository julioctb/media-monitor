import { error, fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	ApiError,
	createSavedSearch,
	deleteSavedSearch,
	getSourceReadiness,
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
	const status = errorStatus(cause, 502);
	const message = errorMessage(cause, 'error desconocido');
	return failure(action, status, message, name);
}

export const load: PageServerLoad = async () => {
	try {
		// Readiness may be unavailable (API hiccup) without killing the page:
		// null simply skips the create-time guard below.
		const sourceReadiness = await getSourceReadiness().catch(() => null);
		return { savedSearches: await listSavedSearches(), sources: SOURCES, sourceReadiness };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudieron cargar las búsquedas guardadas: ${detail}`);
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

		if (!name) return failure('create', 400, 'El nombre es obligatorio.');
		if (name.length > MAX_NAME)
			return failure('create', 400, `El nombre admite hasta ${MAX_NAME} caracteres.`, name);
		if (!query) return failure('create', 400, 'La consulta es obligatoria.', name);
		if (query.length > MAX_QUERY)
			return failure('create', 400, `La consulta admite hasta ${MAX_QUERY} caracteres.`, name);
		if (range_days < 1 || range_days > 365)
			return failure('create', 400, 'El rango debe estar entre 1 y 365 días.', name);

		const readiness = await getSourceReadiness().catch(() => null);
		if (readiness) {
			const unready = sources.filter((source) => !readiness[source]);
			if (unready.length > 0) {
				return failure(
					'create',
					400,
					`Sin credenciales para: ${unready.join(', ')}. Configura la fuente antes de filtrar por ella.`,
					name
				);
			}
		}

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
				message: `Búsqueda guardada “${saved.name}” creada.`,
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
			return failure('toggle', 400, 'Identificador inválido.');
		}

		try {
			await updateSavedSearch(id, { is_active: isActive });
			return {
				action: 'toggle',
				ok: true,
				message: isActive ? 'Búsqueda guardada activada.' : 'Búsqueda guardada pausada.',
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
			return failure('delete', 400, 'Identificador inválido.');
		}

		try {
			await deleteSavedSearch(id);
			return { action: 'delete', ok: true, message: 'Búsqueda guardada eliminada.', name: '' };
		} catch (cause) {
			return apiFailure('delete', cause);
		}
	}
};
