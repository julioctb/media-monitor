import { json } from '@sveltejs/kit';
import { ApiError, getPerson } from '$lib/api';
import type { RequestHandler } from './$types';

function boundedInteger(value: string | null, fallback: number, minimum: number, maximum: number): number {
	const parsed = Number(value ?? fallback);
	return Number.isInteger(parsed) && parsed >= minimum ? Math.min(parsed, maximum) : fallback;
}

export const GET: RequestHandler = async ({ params, url }) => {
	const id = Number(params.id);
	if (!Number.isInteger(id) || id <= 0) return json({ message: 'Persona no encontrada' }, { status: 404 });

	const limit = boundedInteger(url.searchParams.get('limit'), 25, 1, 100);
	const offset = boundedInteger(url.searchParams.get('offset'), 0, 0, Number.MAX_SAFE_INTEGER);
	const order = url.searchParams.get('order') === 'oldest' ? 'oldest' : 'recent';

	try {
		return json(await getPerson(id, { limit, offset, order }));
	} catch (cause) {
		if (cause instanceof ApiError && cause.status === 404) {
			return json({ message: 'Persona no encontrada' }, { status: 404 });
		}
		return json({ message: 'No se pudo cargar la persona' }, { status: 503 });
	}
};
