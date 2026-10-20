/**
 * Derived aggregates for the daily digest (resumen diario).
 *
 * Everything here is computed from data the API already exposes — the
 * day's mention page (sentiment x source) and the digest content
 * itself. No new endpoints: when the day query fails the UI renders
 * the coherent empty state instead.
 */

/** Sources counted as news media; every other tag is social/field. */
export function isNewsSource(source: string): boolean {
	return source === 'gdelt' || source.startsWith('news');
}

export interface ToneCounts {
	positive: number;
	negative: number;
	neutral: number;
	unclassified: number;
	total: number;
}

export function emptyTone(): ToneCounts {
	return { positive: 0, negative: 0, neutral: 0, unclassified: 0, total: 0 };
}

function bump(tone: ToneCounts, sentiment: string | null): void {
	if (sentiment === 'positive') tone.positive += 1;
	else if (sentiment === 'negative') tone.negative += 1;
	else if (sentiment === 'neutral') tone.neutral += 1;
	else tone.unclassified += 1;
	tone.total += 1;
}

/** Media vs social sentiment split for one day of mentions. */
export function splitTones(items: { sentiment: string | null; source: string }[]): {
	media: ToneCounts;
	social: ToneCounts;
} {
	const media = emptyTone();
	const social = emptyTone();
	for (const item of items) bump(isNewsSource(item.source) ? media : social, item.sentiment);
	return { media, social };
}

export interface ToneRow {
	key: 'positive' | 'negative' | 'neutral';
	label: string;
	/** Count, or the fallback string when the bucket is unknowable. */
	value: string;
}

const TONE_KEYS: { key: ToneRow['key']; label: string }[] = [
	{ key: 'positive', label: 'Positiva' },
	{ key: 'negative', label: 'Negativa' },
	{ key: 'neutral', label: 'Neutra' }
];

/**
 * Tone rows for a summary box. `fallback` renders when there is no
 * breakdown at all (mockup: «Sin calcular» / «Sin datos»).
 */
export function toneRows(counts: ToneCounts | undefined, fallback: string): ToneRow[] {
	if (!counts || counts.total === 0) {
		return TONE_KEYS.map(({ key, label }) => ({ key, label, value: fallback }));
	}
	return TONE_KEYS.map(({ key, label }) => ({ key, label, value: String(counts[key]) }));
}

export interface CategoryRow {
	key: string;
	label: string;
	count: number;
	pct: number;
}

/**
 * «Notas por categoría» rows. Percentages are relative to `total`
 * (defaults to the sum of the observed counts).
 */
export function categoryRows(
	byTopic: Record<string, number> | undefined,
	total?: number
): CategoryRow[] {
	if (!byTopic) return [];
	const entries = Object.entries(byTopic).filter(([, count]) => count > 0);
	const sum = total ?? entries.reduce((acc, [, count]) => acc + count, 0);
	if (sum <= 0) return [];
	return entries
		.map(([key, count]) => ({
			key,
			count,
			pct: Math.round((count / sum) * 100),
			label: key
		}))
		.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

/** Overall tones across media + social. */
export function combineTones(a: ToneCounts, b: ToneCounts): ToneCounts {
	return {
		positive: a.positive + b.positive,
		negative: a.negative + b.negative,
		neutral: a.neutral + b.neutral,
		unclassified: a.unclassified + b.unclassified,
		total: a.total + b.total
	};
}

/** Up to two-letter monogram for the actor list («Lilia Cedillo» → LC). */
export function monogram(name: string): string {
	const parts = name
		.trim()
		.split(/\s+/)
		.filter((part) => /[\p{L}]/u.test(part));
	if (parts.length === 0) return '–';
	if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
	return (parts[0][0] + parts[1][0]).toUpperCase();
}
