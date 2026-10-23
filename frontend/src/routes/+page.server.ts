import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	ApiError,
	getClientSettings,
	getDayStats,
	getDailySummary,
	listSummaryDays,
	listMentions,
	listPersons,
	listKeywords
} from '$lib/api';
import { negativeNewsItems } from '$lib/digest-stats';
import { zonedDayBounds } from '$lib/format';
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

/** Live day coverage: totals, topic histogram and distinct events. */
function coverageOf(
	items: { event_id?: number | null; classifications?: { classifier: string; label: string }[] | undefined }[]
): {
	total: number;
	byTopic: Record<string, number>;
	events: number;
} {
	const byTopic: Record<string, number> = {};
	const seenEvents = new Set<number>();
	for (const item of items) {
		for (const classification of item.classifications ?? []) {
			if (classification.classifier === 'topic') {
				byTopic[classification.label] = (byTopic[classification.label] ?? 0) + 1;
			}
		}
		if (item.event_id !== undefined && item.event_id !== null) {
			seenEvents.add(item.event_id);
		}
	}
	return { total: items.length, byTopic, events: seenEvents.size };
}

/**
 * Ingest sources wired on every cycle: google_news + x_index always; the
 * rest per settings (gdelt flag, RSS list, scrapers, Facebook pages).
 * Feeds the «N fuentes activas» note under Resumen general.
 */
function activeSourceCount(settings: {
	gdelt_enabled?: boolean;
	rss_feeds?: string[];
	scrapers?: string[];
	facebook_pages?: unknown[];
} | null): number {
	if (!settings) return 0;
	return (
		2 +
		(settings.gdelt_enabled ? 1 : 0) +
		(settings.rss_feeds?.length ?? 0) +
		(settings.scrapers?.length ?? 0) +
		(settings.facebook_pages?.length ?? 0)
	);
}

/** Redes block labels: plain «Facebook», never the page list. */
function socialLabelsFor(pages: { label: string }[] | undefined): Record<string, string> {
	if (!pages || pages.length === 0) return {};
	return { facebook_page: 'Facebook' };
}

/** First day of the month containing `day` («ver mes anterior» anchor). */
function monthFirst(day: string): string {
	return `${day.slice(0, 7)}-01`;
}

export const load: PageServerLoad = async ({ url }) => {
	const requested = url.searchParams.get('date');
	const requestedDay = requested && DATE_RE.test(requested) ? requested : null;
	// «ver mes anterior»: history pages older than this YYYY-MM-01.
	const beforeParam = url.searchParams.get('before');
	const before = beforeParam && DATE_RE.test(beforeParam) ? beforeParam : null;
	// Single settings read: timezone gate, cut hours, source count, labels.
	const settingsPromise = getClientSettings().catch(() => null);
	// "Today" must follow the client display timezone, not the container
	// clock (UTC): after 18:00 local the UTC date is already tomorrow.
	const day = requestedDay ?? todayIn(((await settingsPromise) ?? undefined)?.timezone || DEFAULT_TZ);
	try {
		// Local-day bounds (same expansion the feed applies): raw date strings
		// become UTC midnights in PG and skew the evening into the next day.
		const bounds = zonedDayBounds(day);
		const [summary, allDays, dayStats, mentionsPage, persons, keywords, settings] =
			await Promise.all([
				getDailySummary(day),
				listSummaryDays().catch(() => []),
				getDayStats(day).catch(() => null),
				listMentions({ since: bounds.since, until: bounds.until, limit: 500 }).catch(() => null),
				listPersons({
					since: bounds.since,
					until: bounds.until,
					limit: 3
				}).catch(() => []),
				listKeywords()
					.then((rows) => rows.filter((keyword) => keyword.is_active))
					.catch(() => []),
				settingsPromise
			]);
		// The visible summary is exactly the requested day's: no digest yet
		// means the legend below renders until the first cut of the day.
		let latestUpdatedAt: string | null = null;
		if (!summary && allDays.length > 0) {
			// The day list carries no timestamp; pull the newest row for the
			// «última actualización» line (null when the lookup fails).
			const latest = await getDailySummary(allDays[0].summary_date).catch(() => null);
			latestUpdatedAt = latest?.updated_at ?? null;
		}
		// History pagination: with ?before=YYYY-MM-01 the sidebar lists the
		// previous months only; the day under view is independent.
		const days = before ? allDays.filter((entry) => entry.summary_date < before) : allDays;
		// «ver mes anterior»: everything before the newest visible month;
		// each click peels one month off the history list.
		const newestVisible = days[0]?.summary_date;
		const olderCandidate = newestVisible ? monthFirst(newestVisible) : null;
		const olderBefore =
			olderCandidate && allDays.some((entry) => entry.summary_date < olderCandidate)
				? olderCandidate
				: null;
		// The mention page feeds the live coverage and the negative-events
		// scan; tone buckets come from /stats/day (media/social/field).
		const liveItems = mentionsPage?.items ?? [];
		return {
			day,
			before,
			summary,
			latest_updated_at: latestUpdatedAt,
			days,
			olderBefore,
			tones: dayStats?.tones ?? null,
			keywordCounts: dayStats?.keywords ?? [],
			negativeEvents: mentionsPage ? negativeNewsItems(liveItems) : [],
			liveCoverage: mentionsPage ? coverageOf(liveItems) : null,
			persons,
			keywords,
			digestHours: settings?.digest_hours ?? [],
			sourcesCount: activeSourceCount(settings),
			socialLabels: socialLabelsFor(settings?.facebook_pages)
		};
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudo cargar el resumen: ${detail}`);
	}
};
