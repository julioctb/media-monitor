import { error } from '@sveltejs/kit';
import {
	ApiError,
	getDailySummary,
	getStatsOverview,
	listKeywords,
	listMentions,
	type Mention,
	type MentionPage,
	type SentimentFilter
} from '$lib/api';
import { channelSources, isFeedChannel, dateRangeError, splitSources, type FeedChannel } from '$lib/feed-filters';
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
	const pool = Math.min(offset + limit, 1000);
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

	// Echo raw values for the form; expand date-only bounds to UTC day edges
	// (the API compares with >= since and <= until).
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
	const since = sinceRaw && DATE_ONLY.test(sinceRaw) ? `${sinceRaw}T00:00:00Z` : sinceRaw || undefined;
	const until = untilRaw && DATE_ONLY.test(untilRaw) ? `${untilRaw}T23:59:59Z` : untilRaw || undefined;

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
		const mentions = rawSource
			? await listMentions({ ...common, source: rawSource, limit, offset })
			: channel === ''
				? await listMentions({ ...common, limit, offset })
				: await loadChannelPage(channelSources(channel, groups), common, limit, offset);

		return {
			mentions,
			keywords,
			digest,
			sourceCounts: stats.by_source,
			channelGroups: groups,
			filters: {
				source: params.get('source') ?? '',
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
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudo cargar el feed: ${detail}`);
	}
};
