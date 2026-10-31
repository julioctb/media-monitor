import { ApiError, askCorpus, getDailySummary, listSummaryDays } from '$lib/api';
import { suggestionQuestions, zonedToday } from '$lib/format';
import type { Actions, PageServerLoad } from './$types';

/**
 * Sugerencias del welcome (mockup queryView): los tres primeros asuntos del
 * digest real del día. Si el día local aún no tiene digest, se toma el último
 * día con síntesis (listSummaryDays), como hace el home con «última
 * actualización». Nunca se inventan preguntas: sin digest no hay chips.
 */
export const load: PageServerLoad = async () => {
	try {
		let summary = await getDailySummary(zonedToday()).catch(() => null);
		if ((summary?.content?.noticias?.length ?? 0) === 0) {
			const days = await listSummaryDays().catch(() => []);
			const latest = days[0]?.summary_date;
			if (latest && latest !== summary?.summary_date) {
				const alt = await getDailySummary(latest).catch(() => null);
				if ((alt?.content?.noticias?.length ?? 0) > 0) summary = alt;
			}
		}
		const suggestions = suggestionQuestions(summary?.content?.noticias);
		let suggestionDate: string | null = null;
		if (suggestions.length > 0 && summary?.summary_date) {
			// «25 oct.» estilo dateShort del mockup; mediodía local para que el
			// parseo de la fecha ISO no corra el día en UTC.
			suggestionDate = new Intl.DateTimeFormat('es-MX', { day: 'numeric', month: 'short' }).format(
				new Date(`${summary.summary_date}T12:00:00`)
			);
		}
		return { suggestions, suggestionDate };
	} catch {
		return { suggestions: [] as string[], suggestionDate: null };
	}
};

export const actions: Actions = {
	default: async ({ request }) => {
		const form = await request.formData();
		const question = String(form.get('question') ?? '').trim();
		if (question.length < 3) {
			return { question, turn: Date.now(), error: 'Escribe una pregunta de al menos 3 caracteres.' };
		}

		try {
			const result = await askCorpus(question);
			return { question, turn: Date.now(), ...result };
		} catch (cause) {
			const detail =
				cause instanceof ApiError
					? cause.message
					: cause instanceof Error
						? cause.message
						: 'error desconocido';
			// Inline error: the question stays on screen, no hard redirect.
			return { question, turn: Date.now(), error: `No se pudo consultar: ${detail}` };
		}
	}
};
