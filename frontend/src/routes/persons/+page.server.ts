import { error } from '@sveltejs/kit';
import { ApiError, listPersons } from '$lib/api';
import type { PageServerLoad } from './$types';

const SORTS = new Set(['mentions', 'recent']);
const VIEWS = new Set(['cards', 'table']);

export const load: PageServerLoad = async ({ url }) => {
	const sortParam = url.searchParams.get('sort') ?? 'mentions';
	const sort = SORTS.has(sortParam) ? (sortParam as 'mentions' | 'recent') : 'mentions';
	const viewParam = url.searchParams.get('view') ?? 'cards';
	const view = VIEWS.has(viewParam) ? (viewParam as 'cards' | 'table') : 'cards';
	const q = url.searchParams.get('q')?.trim() || undefined;

	try {
		return { persons: await listPersons({ sort, q, limit: 200 }), sort, view, q: q ?? '' };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudieron cargar las personas: ${detail}`);
	}
};
