import { error, json } from '@sveltejs/kit';
import { ApiError, getPerson } from '$lib/api';
import type { RequestHandler } from './$types';

/**
 * Read-only ficha bridge for the directory dialog: the browser fetches the
 * same person detail the /persons/[id] load uses, served server-to-server
 * (the backend exposes no CORS and the browser never calls it directly).
 */
export const GET: RequestHandler = async ({ params }) => {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) throw error(404, 'Persona no encontrada');
	try {
		return json(await getPerson(id));
	} catch (cause) {
		if (cause instanceof ApiError && cause.status === 404) {
			throw error(404, 'Persona no encontrada');
		}
		throw error(502, 'No se pudo cargar la ficha');
	}
};
