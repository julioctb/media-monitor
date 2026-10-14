import { ApiError, askCorpus } from '$lib/api';
import type { Actions } from './$types';

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await request.formData();
		const question = String(form.get('question') ?? '').trim();
		if (question.length < 3) {
			return { question, error: 'Escribe una pregunta de al menos 3 caracteres.' };
		}

		try {
			const result = await askCorpus(question);
			return { question, ...result };
		} catch (cause) {
			const detail =
				cause instanceof ApiError
					? cause.message
					: cause instanceof Error
						? cause.message
						: 'error desconocido';
			// Inline error: the question stays on screen, no hard redirect.
			return { question, error: `No se pudo consultar: ${detail}` };
		}
	}
};
