import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import { listPersons } from '$lib/api';
import { PERSONS_DIRECTORY_LIMIT } from '$lib/persons';
import { MM_PREFS_COOKIE, parsePrefs } from '$lib/prefs';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ url, cookies }) => {
	const q = url.searchParams.get('q')?.trim() || undefined;
	try {
		// Load at most 200 ranked identities; local ascending/follow filters and
		// their counts describe this bounded pool, not the global directory.
		// Followed-person ids come from the mm_prefs cookie so the segmented
		// «Todos / En seguimiento» and its header count render on first paint
		// (same seed pattern as /events).
		return {
			persons: await listPersons({ sort: 'mentions', q, limit: PERSONS_DIRECTORY_LIMIT }),
			q: q ?? '',
			prefs: parsePrefs(cookies.get(MM_PREFS_COOKIE))
		};
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudieron cargar las personas: ${detail}`);
	}
};
