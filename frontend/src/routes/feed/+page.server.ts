import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	ApiError,
	getDailySummary,
	getEvent,
	getStatsOverview,
	getFeedStats,
	listAgendaItems,
	listKeywords,
	listMentions,
	type AgendaItem,
	type EventDetail,
	type FeedStats,
	type Mention,
	type MentionPage,
	type SentimentFilter
} from '$lib/api';
import { channelSources, isFeedChannel, dateRangeError, splitSources, type FeedChannel } from '$lib/feed-filters';
import { MM_PREFS_COOKIE, parsePrefs } from '$lib/prefs';
import { channelLabelFor, displayDayKey, zonedDayBounds } from '$lib/format';
import type { PageServerLoad } from './$types';

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const SENTIMENT_FILTERS = new Set<SentimentFilter>(['positive', 'negative', 'neutral', 'none']);
const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;
/** Personas identificadas: un solo pool del periodo con el cap del API
 * (app/api/mentions.py Query le=500) — mismo patrón documentado del
 * channel-pool; el agregado vive server-side, nunca en el cliente. */
const PERSON_POOL_LIMIT = 500;
/** «Próximas fechas» (mockup asideContent): primeras 2 por fecha. */
const UPCOMING_LIMIT = 2;

/** One «Eventos en foco» row: followed event with mentions in the window. */
interface FocusEventRow {
	id: number;
	title: string;
	/** Mentions of the event inside the loaded period. */
	mentions: number;
	/** Distinct channel labels among them (mockup «tipos de fuente»). */
	sourceKinds: number;
}
function intParam(params: URLSearchParams, key: string, fallback: number, min: number, max: number): number {
	const raw = params.get(key);
	if (raw === null || !/^\d+$/.test(raw.trim())) return fallback;
	const value = Number.parseInt(raw, 10);
	return Number.isNaN(value) ? fallback : Math.min(max, Math.max(min, value));
}

interface MentionQueryCommon {
	sentiment?: SentimentFilter;
	keyword_id?: number;
	classifier?: string;
	label?: string;
	since?: string;
	until?: string;
	q?: string;
}

const byRecency = (a: Mention, b: Mention): number => {
	const aAt = a.published_at ?? a.ingested_at;
	const bAt = b.published_at ?? b.ingested_at;
	return aAt < bAt ? 1 : aAt > bAt ? -1 : b.id - a.id;
};

/**
 * Event-detail payload for every distinct event referenced by the loaded
 * page (mockup eventDetail dialog data). One getEvent per distinct id; a
 * failed fetch degrades that chip to the /events page link, never the page.
 */
async function loadEventsById(items: Mention[], followed: number[] = []): Promise<Record<number, EventDetail>> {
	const ids = [
		...new Set([
			...items.map((m) => m.event_id).filter((id): id is number => id !== null),
			...followed
		])
	];
	const settled = await Promise.allSettled(ids.map((id) => getEvent(id)));
	const byId: Record<number, EventDetail> = {};
	settled.forEach((result, index) => {
		if (result.status === 'fulfilled') byId[ids[index]] = result.value;
	});
	return byId;
}

/**
 * Focus panel rows (mockup focusEvents): followed events with at least one
 * mention inside the loaded period. Counts read the SAME EventDetail
 * payloads as the event chips — one getEvent per id, a failed fetch drops
 * that row silently, never the page. The window mirrors the list query:
 * mention publication inside since/until (all mentions when unbounded).
 */
function focusRows(
	followed: number[],
	details: Record<number, EventDetail>,
	since: string | undefined,
	until: string | undefined
): FocusEventRow[] {
	const sinceAt = since ? new Date(since).getTime() : null;
	const untilAt = until ? new Date(until).getTime() : null;
	const inWindow = (publishedAt: string | null): boolean => {
		if (sinceAt === null && untilAt === null) return true;
		if (!publishedAt) return false;
		const at = new Date(publishedAt).getTime();
		if (Number.isNaN(at)) return false;
		if (sinceAt !== null && at < sinceAt) return false;
		if (untilAt !== null && at > untilAt) return false;
		return true;
	};
	return followed.flatMap((id) => {
		const detail = details[id];
		if (!detail) return []; // silent per-row degradation
		const windowed = detail.mentions.filter((mention) => inWindow(mention.published_at));
		if (windowed.length === 0) return [];
		return [
			{
				id,
				title: detail.title,
				mentions: windowed.length,
				sourceKinds: new Set(windowed.map((mention) => channelLabelFor(mention.source))).size
			}
		];
	});
}

/** «Personas identificadas» row: persona referida por el pool del periodo. */
interface PersonMentionRow {
	id: number;
	name: string;
	/** Menciones del pool que nombran a la persona. */
	mentions: number;
}

/**
 * Personas identificadas (mockup asideContent): personas únicas del pool
 * del periodo con su conteo de menciones, desc por menciones. El pool
 * llega por recencia descendente, y el sort estable la conserva como
 * desempate (clave secundaria del mockup). Un pool fallido degrada a
 * cero filas — mismo patrón silencioso de focusEvents, nunca la página.
 */
function aggregatePersons(items: Mention[]): PersonMentionRow[] {
	const counts = new Map<number, { name: string; mentions: number }>();
	for (const mention of items) {
		const seen = new Set<number>();
		for (const person of mention.persons ?? []) {
			if (seen.has(person.id)) continue;
			seen.add(person.id);
			const row = counts.get(person.id);
			if (row) row.mentions += 1;
			else counts.set(person.id, { name: person.name, mentions: 1 });
		}
	}
	return [...counts.entries()]
		.map(([id, row]) => ({ id, ...row }))
		.sort((a, b) => b.mentions - a.mentions);
}

/** «Próximas fechas» row: entrada de agenda con fecha real, lista para pintar. */
interface UpcomingAgendaRow {
	id: number;
	title: string;
	/** YYYY-MM-DD; las filas sin fecha nunca llegan aquí. */
	eventDate: string;
	/** Hora solo cuando la entrada la trae (condicional del mockup). */
	timeLabel: string | null;
}

/**
 * Próximas fechas (mockup asideContent): entradas de agenda desde hoy
 * (día calendario local), primeras 2 por fecha. El mock lee events con
 * date; el API de eventos no expone fecha de evento (solo first/last
 * seen), así que la agenda — la fuente real de compromisos del app — la
 * sustituye (divergencia semántica documentada en la vista).
 */
function upcomingAgendaRows(items: AgendaItem[], todayIso: string): UpcomingAgendaRow[] {
	return items
		.filter(
			(item): item is AgendaItem & { event_date: string } =>
				item.event_date !== null && item.event_date >= todayIso
		)
		.sort((a, b) => a.event_date.localeCompare(b.event_date))
		.slice(0, UPCOMING_LIMIT)
		.map((item) => ({
			id: item.id,
			title: item.title,
			eventDate: item.event_date,
			timeLabel: item.time_label
		}));
}

/**
 * Channel filters span several sources and the API takes one per query:
 * fetch each source's newest `pool` rows, merge by recency and slice the
 * requested page. Totals come from the per-source counts, so they are
 * exact even when the merged pool truncates deep offsets.
 */
async function loadChannelPage(
	channelSources: string[],
	common: MentionQueryCommon,
	limit: number,
	offset: number
): Promise<MentionPage> {
	if (channelSources.length === 0) {
		return { items: [], total: 0 };
	}
	// The API caps limit at 500 (app/api/mentions.py Query le=500); a deeper
	// pool 422s and the page degrades to null.
	const pool = Math.min(offset + limit, 500);
	const pages = await Promise.all(
		channelSources.map((source) =>
			listMentions({ ...common, source, limit: pool, offset: 0 })
		)
	);
	const merged = pages
		.flatMap((page) => page.items)
		.sort(byRecency)
		.slice(offset, offset + limit);
	return { items: merged, total: pages.reduce((sum, page) => sum + page.total, 0) };
}

export const load: PageServerLoad = async ({ url, cookies }) => {
	const params = url.searchParams;

	// User prefs (saved/follow/seen) ride one cookie; server-side readers:
	// the focus panel rows and the card states. Tolerant parse.
	const prefs = parsePrefs(cookies.get(MM_PREFS_COOKIE));

	// Echo raw values for the form; expand date-only bounds to full local
	// days in the display timezone (the API compares with >= since and
	// <= until; UTC days would skew the local evening into the next day).
	const rawSource = params.get('source')?.trim() || undefined;
	const rawChannel = params.get('channel')?.trim() ?? '';
	const channel: FeedChannel = isFeedChannel(rawChannel) ? rawChannel : '';
	const rawSentiment = params.get('sentiment')?.trim() || undefined;
	const sentiment = rawSentiment && SENTIMENT_FILTERS.has(rawSentiment as SentimentFilter)
		? (rawSentiment as SentimentFilter)
		: undefined;
	const rawKeyword = params.get('keyword_id')?.trim() ?? '';
	const keywordId = /^\d+$/.test(rawKeyword) ? Number(rawKeyword) : undefined;
	const q = params.get('q')?.trim() || undefined;

	const sinceRaw = params.get('since')?.trim() || '';
	const untilRaw = params.get('until')?.trim() || '';
	const since = DATE_ONLY.test(sinceRaw) ? zonedDayBounds(sinceRaw).since : sinceRaw || undefined;
	const until = DATE_ONLY.test(untilRaw) ? zonedDayBounds(untilRaw).until : untilRaw || undefined;

	const limit = intParam(params, 'limit', DEFAULT_LIMIT, 1, MAX_LIMIT);
	const offset = intParam(params, 'offset', 0, 0, Number.MAX_SAFE_INTEGER);

	// 'Solo políticas' checkbox: one param expands to the classifier probe
	// classifier=political + label=political (v1's only facet).
	const politicalOnly = params.get('political')?.trim() === '1';

	const common: MentionQueryCommon = {
		sentiment,
		keyword_id: keywordId,
		classifier: politicalOnly ? 'political' : undefined,
		label: politicalOnly ? 'political' : undefined,
		since,
		until,
		q
	};

	try {
		// Stats only provides the source facet: the source set is open, so the
		// filter options come from data, never a hardcoded enum. The digest is
		// best-effort: an absent/unbuilt day must not break the feed.
		const todayIso = new Date().toISOString().slice(0, 10);
		const keywords = await listKeywords();
		// «Hoy» calendario en zona de visualización: frontera de «Próximas
		// fechas» (el corte UTC de arriba es la clave del digest, no esta).
		const todayLocal = displayDayKey(new Date().toISOString());
		// Paneles del aside (personas agregadas + agenda): lecturas
		// best-effort junto a stats; un fallo deja el panel en su empty
		// state, nunca tumba la página. Pool única cap 500 = patrón
		// channel-pool.
		const [stats, digest, periodPool, agendaRows] = await Promise.all([
			getStatsOverview(),
			getDailySummary(todayIso).catch(() => null),
			listMentions({ ...common, limit: PERSON_POOL_LIMIT })
				.then((page) => page.items)
				.catch(() => null),
			listAgendaItems().catch(() => [])
		]);

		const groups = splitSources(Object.keys(stats.by_source).sort());
		// medium (outlet host) narrows server-side; it wins over the channel
		// pools the same way an explicit source does.
		const rawMedium = params.get('medium')?.trim() || undefined;
		const mentions = rawMedium
			? await listMentions({ ...common, source: rawSource, medium: rawMedium, limit, offset })
			: rawSource
				? await listMentions({ ...common, source: rawSource, limit, offset })
				: channel === ''
					? await listMentions({ ...common, limit, offset })
					: await loadChannelPage(channelSources(channel, groups), common, limit, offset);

		const metricSources = !rawMedium && !rawSource && channel !== ''
			? channelSources(channel, groups)
			: undefined;
		const eventsById = await loadEventsById(mentions.items, prefs.follow);

		// Paneles del aside: personas del pool del periodo y próximas fechas.
		const persons = periodPool ? aggregatePersons(periodPool) : [];
		const agendaUpcoming = upcomingAgendaRows(agendaRows, todayLocal);

		let feedStats: FeedStats | null = null;
		let feedStatsError: string | null = null;
		try {
			// [] is unrestricted in the shared query builder, not match-none.
			// Metrics keep the full tone distribution of the current scope
			// (mockup toneFilterView counts feedBase(): source/period/q apply,
			// the tone filter itself does NOT zero the other tones).
			const { sentiment: _tone, ...scope } = common;
			feedStats = metricSources?.length === 0
				? {
					total: 0,
					by_source: Object.fromEntries(Object.keys(stats.by_source).map((source) => [source, 0])),
					by_sentiment: { positive: 0, negative: 0, neutral: 0, none: 0 },
					news_medium_count: 0,
					result_group_count: 0
				}
				: await getFeedStats({
					...scope, source: rawSource, medium: rawMedium, sources: metricSources
				});
		} catch (cause) {
			// A separate read failing must not discard an already loaded page.
			feedStatsError = `Indicadores no disponibles: ${errorMessage(cause, 'error desconocido')}`;
		}

		return {
			feedStats,
			feedStatsError,
			mentions,
			keywords,
			digest,
			sourceCounts: stats.by_source,
			mediumCounts: stats.by_medium ?? {},
			newsMediumCount: stats.news_medium_count ?? 0,
			channelGroups: groups,
			eventsById: eventsById,
			focusEvents: focusRows(prefs.follow, eventsById, since, until),
			persons,
			agendaUpcoming,
			prefs,
			filters: {
				source: params.get('source') ?? '',
				medium: params.get('medium') ?? '',
				channel,
				sentiment: params.get('sentiment') ?? '',
				keyword_id: rawKeyword,
				political: params.get('political') ?? '',
				since: sinceRaw,
				until: untilRaw,
				dateError: dateRangeError(sinceRaw, untilRaw),
				q: params.get('q') ?? '',
				limit,
				offset
			}
		};
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudo cargar el feed: ${detail}`);
	}
};
