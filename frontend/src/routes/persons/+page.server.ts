import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import { ApiError, listPersons } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url }) => {
	const q = url.searchParams.get('q')?.trim() || undefined;
	try {
		// Fixed relevance order (mentions) while the sort control is out of the UI.
		return { persons: await listPersons({ sort: 'mentions', q, limit: 200 }), q: q ?? '' };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudieron cargar las personas: ${detail}`);
	}
};
