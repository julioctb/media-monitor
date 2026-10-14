import { error } from '@sveltejs/kit';
import { ApiError, listEvents } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		// The feed is newest-seen first server side; one page is plenty for v1.
		return { events: await listEvents({ limit: 100 }) };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudieron cargar los eventos: ${detail}`);
	}
};
