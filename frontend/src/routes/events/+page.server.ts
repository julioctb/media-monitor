import { error } from '@sveltejs/kit';
import { ApiError, listEvents } from '$lib/api';
import type { PageServerLoad } from './$types';

const SCOPES = new Set(['eco', 'todas']);

export const load: PageServerLoad = async ({ url }) => {
	const scopeParam = url.searchParams.get('scope') ?? 'eco';
	const scope = SCOPES.has(scopeParam) ? (scopeParam as 'eco' | 'todas') : 'eco';

	try {
		// 'eco' = historias con cobertura real (2+ menciones); las de una sola
		// nota son duplicados del feed y viven tras el toggle.
		const events = await listEvents({
			limit: 200,
			min_mentions: scope === 'eco' ? 2 : 1
		});
		return { events, scope };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudieron cargar los eventos: ${detail}`);
	}
};
