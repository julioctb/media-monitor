import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import { ApiError, getStatsOverview, listSpikes } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const [stats, spikes] = await Promise.all([getStatsOverview(), listSpikes({ days: 30 })]);
		return { stats, spikes };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudieron cargar las estadísticas: ${detail}`);
	}
};
