import { error } from '@sveltejs/kit';
import { ApiError, getStatsOverview, listSpikes } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const [stats, spikes] = await Promise.all([getStatsOverview(), listSpikes({ days: 30 })]);
		return { stats, spikes };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudieron cargar las estadísticas: ${detail}`);
	}
};
