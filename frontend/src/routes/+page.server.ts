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
type MentionLike = {
	event_id?: number | null;
	sentiment?: string | null;
};

/** Majority sentiment per canonical event, for the digest news pills. */
function majoritySentimentByEvent(items: MentionLike[]): Record<string, string> {
	const tally: Record<string, Record<string, number>> = {};
	for (const item of items) {
		if (!item.event_id || !item.sentiment || item.sentiment === 'none') continue;
		const key = String(item.event_id);
		const bucket = (tally[key] ??= {});
		bucket[item.sentiment] = (bucket[item.sentiment] ?? 0) + 1;
	}
	const out: Record<string, string> = {};
	for (const [key, counts] of Object.entries(tally)) {
		out[key] = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
	}
	return out;
}

async function loadSideData(day: string) {
	const [mentionsResult, persons, keywords] = await Promise.all([
		listMentions({ since: day, until: nextDay(day), limit: 200 })
			.then((page) => ({
				tones: splitTones(page.items),
				eventSentiment: majoritySentimentByEvent(page.items)
			}))
			.catch(() => null),
		listPersons({ sort: 'mentions', limit: 3 }).catch(() => []),
		listKeywords()
			.then((rows) => rows.filter((keyword) => keyword.is_active))
			.catch(() => [])
	]);
	const tones = mentionsResult?.tones ?? null;
	const eventSentiment = mentionsResult?.eventSentiment ?? {};
	return { tones, eventSentiment, persons, keywords };
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
		let visible = summary;
		// No digest for the requested day (the worker builds it at 21:00):
		// fall back to the latest published one so the home is never bare.
		// An explicitly picked date keeps its empty state.
		if (!visible && !requested && days.length > 0) {
			const latest = days[0].summary_date;
			visible = await getDailySummary(latest);
			if (visible) day = latest;
		}
		const side = visible
			? await loadSideData(day)
			: { tones: null, eventSentiment: {}, persons: [], keywords: [] };
		return { day, summary: visible, days, ...side };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudo cargar el resumen: ${detail}`);
	}
};
