import { error } from '@sveltejs/kit';
import { ApiError, getStatsOverview, listKeywords, listMentions, type SentimentFilter } from '$lib/api';
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

export const load: PageServerLoad = async ({ url }) => {
	const params = url.searchParams;

	// Echo raw values for the form; expand date-only bounds to UTC day edges
	// (the API compares with >= since and <= until).
	const rawSource = params.get('source')?.trim() || undefined;
	const rawSentiment = params.get('sentiment')?.trim() || undefined;
	const sentiment = rawSentiment && SENTIMENT_FILTERS.has(rawSentiment as SentimentFilter)
		? (rawSentiment as SentimentFilter)
		: undefined;
	const rawKeyword = params.get('keyword_id')?.trim() ?? '';
	const keywordId = /^\d+$/.test(rawKeyword) ? Number(rawKeyword) : undefined;
	const q = params.get('q')?.trim() || undefined;

	const sinceRaw = params.get('since')?.trim() || undefined;
	const untilRaw = params.get('until')?.trim() || undefined;
	const since = sinceRaw && DATE_ONLY.test(sinceRaw) ? `${sinceRaw}T00:00:00Z` : sinceRaw;
	const until = untilRaw && DATE_ONLY.test(untilRaw) ? `${untilRaw}T23:59:59Z` : untilRaw;

	const limit = intParam(params, 'limit', DEFAULT_LIMIT, 1, MAX_LIMIT);
	const offset = intParam(params, 'offset', 0, 0, Number.MAX_SAFE_INTEGER);

	try {
		// Stats only provides the source facet: the source set is open, so the
		// filter options come from data, never a hardcoded enum.
		const [mentions, keywords, stats] = await Promise.all([
			listMentions({ source: rawSource, sentiment, keyword_id: keywordId, since, until, q, limit, offset }),
			listKeywords(),
			getStatsOverview()
		]);

		return {
			mentions,
			keywords,
			sources: Object.keys(stats.by_source).sort(),
			filters: {
				source: params.get('source') ?? '',
				sentiment: params.get('sentiment') ?? '',
				keyword_id: rawKeyword,
				since: params.get('since') ?? '',
				until: params.get('until') ?? '',
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
