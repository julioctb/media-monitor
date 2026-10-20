import { error } from '@sveltejs/kit';
import { ApiError, listKeywords } from '$lib/api';
import { handleKeywordCreate, handleKeywordDelete, handleKeywordToggle } from '$lib/keyword-actions';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		return { keywords: await listKeywords() };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudieron cargar las palabras clave: ${detail}`);
	}
};

export const actions: Actions = {
	create: ({ request }) => handleKeywordCreate(request),
	toggle: ({ request }) => handleKeywordToggle(request),
	delete: ({ request }) => handleKeywordDelete(request)
};
