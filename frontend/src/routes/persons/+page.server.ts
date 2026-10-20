import { error } from '@sveltejs/kit';
import { ApiError, listPersons } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const q = url.searchParams.get('q')?.trim() || undefined;
	try {
		// Fixed relevance order (mentions) while the sort control is out of the UI.
		return { persons: await listPersons({ sort: 'mentions', q, limit: 200 }), q: q ?? '' };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudieron cargar las personas: ${detail}`);
	}
};
