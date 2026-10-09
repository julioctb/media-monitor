import { error, fail } from '@sveltejs/kit';
import { ApiError, createKeyword, deleteKeyword, listKeywords, updateKeyword } from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const LANGUAGES = new Set(['es', 'en']);
const MAX_TEXT_LENGTH = 500;

/** Uniform action result: every branch carries the same keys for the view. */
interface KeywordActionResult {
	action: 'create' | 'toggle' | 'delete';
	ok: boolean;
	message: string;
	text: string;
}

function failure(action: KeywordActionResult['action'], status: number, message: string, text = '') {
	return fail(status, { action, ok: false, message, text } satisfies KeywordActionResult);
}

function apiFailure(action: KeywordActionResult['action'], cause: unknown, text = '') {
	const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 502;
	const message = cause instanceof Error ? cause.message : 'error desconocido';
	return failure(action, status, message, text);
}

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
	create: async ({ request }) => {
		const form = await request.formData();
		const text = String(form.get('text') ?? '').trim();
		const languageRaw = String(form.get('language') ?? 'es');
		const language = (LANGUAGES.has(languageRaw) ? languageRaw : 'es') as 'es' | 'en';

		if (!text) {
			return failure('create', 400, 'El texto de la palabra clave es obligatorio.');
		}
		if (text.length > MAX_TEXT_LENGTH) {
			return failure('create', 400, `Máximo ${MAX_TEXT_LENGTH} caracteres.`, text);
		}

		try {
			const keyword = await createKeyword({ text, language });
			// Success: SvelteKit re-runs every load function (invalidateAll), so the
			// list below reflects the new row without extra work here.
			return {
				action: 'create',
				ok: true,
				message: `Palabra clave «${keyword.text}» agregada.`,
				text: ''
			} satisfies KeywordActionResult;
		} catch (cause) {
			return apiFailure('create', cause, text);
		}
	},

	toggle: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		const isActive = String(form.get('is_active')) === '1';

		if (!Number.isInteger(id) || id <= 0) {
			return failure('toggle', 400, 'Identificador inválido.');
		}

		try {
			await updateKeyword(id, { is_active: isActive });
			return {
				action: 'toggle',
				ok: true,
				message: isActive ? 'Palabra clave activada.' : 'Palabra clave desactivada.',
				text: ''
			} satisfies KeywordActionResult;
		} catch (cause) {
			return apiFailure('toggle', cause);
		}
	},

	delete: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));

		if (!Number.isInteger(id) || id <= 0) {
			return failure('delete', 400, 'Identificador inválido.');
		}

		try {
			await deleteKeyword(id);
			return { action: 'delete', ok: true, message: 'Palabra clave eliminada.', text: '' };
		} catch (cause) {
			// 409 carries the backend detail: how many mentions reference it.
			return apiFailure('delete', cause);
		}
	}
};
