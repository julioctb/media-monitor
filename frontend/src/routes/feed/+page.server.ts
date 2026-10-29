import { error } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	ApiError,
	getDailySummary,
	getEvent,
	getStatsOverview,
	getFeedStats,
	listKeywords,
	listMentions,
	type EventDetail,
	type FeedStats,
	type Mention,
	type MentionPage,
	type SentimentFilter
} from '$lib/api';
import { channelSources, isFeedChannel, dateRangeError, splitSources, type FeedChannel } from '$lib/feed-filters';
import { zonedDayBounds } from '$lib/format';
import type { PageServerLoad } from './$types';

const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const SENTIMENT_FILTERS = new Set<SentimentFilter>(['positive', 'negative', 'neutral', 'none']);
const DEFAULT_LIMIT = 50;
const MAX_LIMIT = 200;
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
async function loadEventsById(items: Mention[]): Promise<Record<number, EventDetail>> {
	const ids = [...new Set(items.map((m) => m.event_id).filter((id): id is number => id !== null))];
	const settled = await Promise.allSettled(ids.map((id) => getEvent(id)));
	const byId: Record<number, EventDetail> = {};
	settled.forEach((result, index) => {
		if (result.status === 'fulfilled') byId[ids[index]] = result.value;
	});
	return byId;
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

export const load: PageServerLoad = async ({ url }) => {
	const params = url.searchParams;

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
		const [stats, digest] = await Promise.all([
			getStatsOverview(),
			getDailySummary(todayIso).catch(() => null)
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
			eventsById: await loadEventsById(mentions.items),
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
