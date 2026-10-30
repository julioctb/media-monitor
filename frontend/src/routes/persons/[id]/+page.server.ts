import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import { ApiError, getPerson } from '$lib/api';
import { MM_PREFS_COOKIE, parsePrefs } from '$lib/prefs';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params, cookies }) => {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) throw error(404, 'Persona no encontrada');

	try {
		// mm_prefs cookie seeds the «Seguir persona» button on first paint.
		return { person: await getPerson(id), prefs: parsePrefs(cookies.get(MM_PREFS_COOKIE)) };
	} catch (cause) {
		if (cause instanceof ApiError && cause.status === 404) {
			throw error(404, 'Persona no encontrada');
		}
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudo cargar la persona: ${detail}`);
	}
};
