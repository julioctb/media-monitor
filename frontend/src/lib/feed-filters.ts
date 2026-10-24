import { isNewsSource } from './digest-stats';

/** Field-prefixed sources are the human channel (reportes de campo). */
export function isFieldSource(source: string): boolean {
	return source.startsWith('field');
}

/**
 * Feed channel filters (feed mockup pills): Todo / Noticias / Redes
 * sociales / Datos de campo. The API accepts a single source per query,
 * so a channel expands to the source set the stats endpoint reported;
 * the page merges those queries.
 */
export type FeedChannel = '' | 'news' | 'social' | 'field';

export const CHANNEL_LABELS: Record<Exclude<FeedChannel, ''> | 'all', string> = {
	all: 'Todo',
	news: 'Noticias',
	social: 'Redes sociales',
	field: 'Datos de campo'
};

export function isFeedChannel(value: string | null | undefined): value is FeedChannel {
	return value === '' || value === 'news' || value === 'social' || value === 'field';
}

/** Partition the known source tags into news / social / field buckets. */
export function splitSources(all: string[]): {
	news: string[];
	social: string[];
	field: string[];
} {
	const news = all.filter((source) => isNewsSource(source) && !isFieldSource(source));
	const social = all.filter((source) => !isNewsSource(source) && !isFieldSource(source));
	const field = all.filter((source) => isFieldSource(source));
	return { news, social, field };
}

/** Sources for a channel; empty array = channel has no ingest yet. */
export function channelSources(
	channel: FeedChannel,
	sources: { news: string[]; social: string[]; field: string[] }
): string[] {
	if (channel === 'news') return sources.news;
	if (channel === 'social') return sources.social;
	if (channel === 'field') return sources.field;
	return [];
}

/** Inline validation for the always-visible date range. */
export function dateRangeError(since: string, until: string): string | null {
	if (!since || !until) return null;
	return since > until ? 'La fecha inicial no puede ser posterior a la fecha final.' : null;
}
