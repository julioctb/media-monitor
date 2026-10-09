import { error, fail, redirect } from '@sveltejs/kit';
import {
	ApiError,
	generateDailySummary,
	getDailySummary,
	listSummaryDays
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/** Server-local today as YYYY-MM-DD; the date input's default. */
function todayIso(): string {
	const now = new Date();
	const mm = String(now.getMonth() + 1).padStart(2, '0');
	const dd = String(now.getDate()).padStart(2, '0');
	return `${now.getFullYear()}-${mm}-${dd}`;
}

function dayFromForm(value: FormDataEntryValue | null): string | null {
	const raw = String(value ?? '').trim();
	return DATE_RE.test(raw) ? raw : null;
}

export const load: PageServerLoad = async ({ url }) => {
	const requested = url.searchParams.get('date');
	const day = requested && DATE_RE.test(requested) ? requested : todayIso();
	try {
		const [summary, days] = await Promise.all([
			getDailySummary(day),
			listSummaryDays().catch(() => [])
		]);
		return { day, summary, days };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudo cargar el resumen: ${detail}`);
	}
};

export const actions: Actions = {
	/** Plain navigation: re-read the picked day through the load above. */
	view: async ({ request }) => {
		const form = await request.formData();
		const day = dayFromForm(form.get('date'));
		redirect(303, day ? `/summary?date=${day}` : '/summary');
	},

	generate: async ({ request }) => {
		const form = await request.formData();
		const day = dayFromForm(form.get('date'));
		let generated;
		try {
			// Empty/invalid date defers to the API: today in the client tz.
			generated = await generateDailySummary(day);
		} catch (cause) {
			const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 502;
			const message = cause instanceof Error ? cause.message : 'error desconocido';
			return fail(status, { action: 'generate', ok: false, message });
		}
		redirect(303, `/summary?date=${generated.summary_date}`);
	}
};
