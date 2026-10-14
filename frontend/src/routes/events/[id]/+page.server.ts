import { error } from '@sveltejs/kit';
import { getEvent, getEventCoverage } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const eventId = Number(params.id);
	if (!Number.isInteger(eventId) || eventId <= 0) {
		throw error(404, 'Evento no encontrado.');
	}

	// Streamed on purpose: the shell renders immediately and each section
	// resolves its own promise (coverage failures must not hide the event).
	return {
		eventId,
		event: getEvent(eventId),
		coverage: getEventCoverage(eventId)
	};
};
