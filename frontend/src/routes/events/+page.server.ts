import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import { listEvents } from '$lib/api';
import { MM_PREFS_COOKIE, parsePrefs } from '$lib/prefs';
import type { PageServerLoad } from './$types';

/**
 * Presentation window, not pagination: the search box and the
 * seguimiento/resto split run client-side over this single pool (same
 * capped-pool pattern as the channel merges' limit 500). Older history stays
 * reachable through the feed and the per-event pages.
 */
const EVENTS_PAGE_LIMIT = 200;

export const load: PageServerLoad = async ({ cookies }) => {
	try {
		// Full population on purpose: «En seguimiento» vs resto is a presentation
		// split (mockup eventCards), so the load must not pre-filter by coverage —
		// the old eco-only default hid every single-mention event.
		const events = await listEvents({ limit: EVENTS_PAGE_LIMIT });
		// Followed ids from the mm_prefs cookie: the card buttons render their
		// pressed state on the server (client writes, server reads).
		const prefs = parsePrefs(cookies.get(MM_PREFS_COOKIE));
		return { events, prefs };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudieron cargar los eventos: ${detail}`);
	}
};
