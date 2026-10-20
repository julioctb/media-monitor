import { error } from '@sveltejs/kit';
import {
	ApiError,
	getClientSettings,
	getDailySummary,
	listSummaryDays,
	listMentions,
	listPersons,
	listKeywords
} from '$lib/api';
import { splitTones } from '$lib/digest-stats';
import type { PageServerLoad } from './$types';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;
const DEFAULT_TZ = 'America/Mexico_City';

/** Calendar date in the display timezone (container may run UTC). */
function todayIn(tz: string): string {
	return new Intl.DateTimeFormat('en-CA', {
		timeZone: tz,
		year: 'numeric',
		month: '2-digit',
		day: '2-digit'
	}).format(new Date());
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
	let day = requested && DATE_RE.test(requested) ? requested : null;
	if (!day) {
		// "Today" must follow the client display timezone, not the container
		// clock (UTC): after 18:00 local the UTC date is already tomorrow.
		const settings = await getClientSettings().catch(() => null);
		day = todayIn(settings?.timezone || DEFAULT_TZ);
	}
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
