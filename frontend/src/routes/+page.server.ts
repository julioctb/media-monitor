import { error, fail, redirect } from '@sveltejs/kit';
import {
	ApiError,
	generateDailySummary,
	getDailySummary,
	listSummaryDays,
	listMentions,
	listPersons,
	listKeywords
} from '$lib/api';
import { splitTones } from '$lib/digest-stats';
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

/** The UTC-day bounds the API expands date-only `since/until` to. */
function nextDay(day: string): string {
	const date = new Date(`${day}T12:00:00Z`);
	date.setUTCDate(date.getUTCDate() + 1);
	return date.toISOString().slice(0, 10);
}

/**
 * Sidebar/summary aggregates: media vs social tone for the day, top
 * tracked actors and active keywords. Each piece degrades to null/[]
 * so a partial API outage keeps the digest readable.
 */
async function loadSideData(day: string) {
	const [mentionsResult, persons, keywords] = await Promise.all([
		listMentions({ since: day, until: nextDay(day), limit: 1000 })
			.then((page) => splitTones(page.items))
			.catch(() => null),
		listPersons({ sort: 'mentions', limit: 3 }).catch(() => []),
		listKeywords()
			.then((rows) => rows.filter((keyword) => keyword.is_active))
			.catch(() => [])
	]);
	return { tones: mentionsResult, persons, keywords };
}

export const load: PageServerLoad = async ({ url }) => {
	const requested = url.searchParams.get('date');
	const day = requested && DATE_RE.test(requested) ? requested : todayIso();
	try {
		const [summary, days] = await Promise.all([
			getDailySummary(day),
			listSummaryDays().catch(() => [])
		]);
		const side = summary ? await loadSideData(day) : { tones: null, persons: [], keywords: [] };
		return { day, summary, days, ...side };
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
