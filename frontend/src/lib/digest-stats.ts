/**
 * Derived aggregates for the daily digest (resumen diario).
 *
 * Everything here is computed from data the API already exposes — the
 * day's mention page and the digest content itself. No new endpoints:
 * when the day query fails the UI renders the coherent empty state.
 */

/** Sources counted as news media; the known social tags are the exception. */
const SOCIAL_SOURCES = new Set(['x_twitter', 'facebook_page']);

export function isNewsSource(source: string): boolean {
	return !SOCIAL_SOURCES.has(source);
}

export interface ToneCounts {
	positive: number;
	negative: number;
	neutral: number;
	unclassified: number;
	total: number;
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
 * «Categorías identificadas» rows. Percentages are relative to `total`
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

/* ----------------------------- home digest v2 ----------------------------- */

/** Noticia counts per event for the home day scan (see negativeNewsItems). */

export interface NegativeNewsItem {
	event_id: number;
	title: string;
	/** Source tag of the item's newest mention; labeled at the edge. */
	source: string;
	/** Publication of that same mention; null when never stamped. */
	published_at: string | null;
}

/** Minimal mention shape the negative-events scan needs. */
type NegativeInput = {
	event_id?: number | null;
	event_title?: string | null;
	title?: string | null;
	source: string;
	sentiment?: string | null;
	published_at?: string | null;
};

interface NegativeCandidate {
	negative: number;
	positive: number;
	neutral: number;
	newest: (NegativeInput & { event_id: number }) | null;
}

/**
 * Events whose classified mentions are majority-negative, worst first.
 * Majority is strict (negative beats positive and neutral); unclassified
 * rows never tip the balance. Title/source ride the event's newest
 * dated mention so the card can show who reported it and when. The
 * display cap (3) lives at the edge, so the total stays known.
 */
export function negativeNewsItems(items: NegativeInput[]): NegativeNewsItem[] {
	const candidates = new Map<number, NegativeCandidate>();
	for (const item of items) {
		if (item.event_id === undefined || item.event_id === null) continue;
		const entry =
			candidates.get(item.event_id) ?? { negative: 0, positive: 0, neutral: 0, newest: null };
		if (item.sentiment === 'negative') entry.negative += 1;
		else if (item.sentiment === 'positive') entry.positive += 1;
		else if (item.sentiment === 'neutral') entry.neutral += 1;
		const stamp = item.published_at ?? '';
		const newestStamp = entry.newest?.published_at ?? '';
		if (!entry.newest || stamp > newestStamp) entry.newest = { ...item, event_id: item.event_id };
		candidates.set(item.event_id, entry);
	}
	const ranked = [...candidates.entries()].filter(
		([, entry]) =>
			entry.negative > 0 &&
			entry.negative > entry.positive &&
			entry.negative > entry.neutral &&
			entry.newest?.title
	);
	ranked.sort((a, b) => b[1].negative - a[1].negative || a[0] - b[0]);
	return ranked.map(([event_id, entry]) => ({
		event_id,
		title: entry.newest?.title ?? '',
		source: entry.newest?.source ?? '',
		published_at: entry.newest?.published_at ?? null
	}));
}

/**
 * Focus-person display name: content stamp first, persona lookup for
 * pre-stamp digests. null = caller renders its own fallback («BUAP»).
 */
export function focusPersonLabel(
	content: { rectora?: { person_id?: number | null; name?: string | null }; personas?: { person_id: number; name: string }[] } | null | undefined
): string | null {
	const rectora = content?.rectora;
	if (!rectora) return null;
	if (rectora.name) return rectora.name;
	const persona = content?.personas?.find((person) => person.person_id === rectora.person_id);
	return persona?.name ?? null;
}
