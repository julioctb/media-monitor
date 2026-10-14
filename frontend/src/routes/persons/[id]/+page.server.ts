import { error } from '@sveltejs/kit';
import { ApiError, getPerson } from '$lib/api';
import type { PageServerLoad } from './$types';

export const load: PageServerLoad = async ({ params }) => {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) throw error(404, 'Persona no encontrada');

	try {
		return { person: await getPerson(id) };
	} catch (cause) {
		if (cause instanceof ApiError && cause.status === 404) {
			throw error(404, 'Persona no encontrada');
		}
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudo cargar la persona: ${detail}`);
	}
};
