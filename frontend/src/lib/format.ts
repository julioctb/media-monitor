/**
 * Presentation helpers. Datetimes are always rendered in UTC, matching the
 * API contract; source labels are derived generically because the source set
 * is open (the backend adds e.g. facebook_page without UI changes).
 */

/** Friendly names for known tags; unknown tags fall through to generic casing. */
const KNOWN_SOURCE_LABELS: Record<string, string> = {
	news_rss: 'News RSS',
	gdelt: 'GDELT',
	x_twitter: 'X (Twitter)'
};

export function sourceLabel(source: string): string {
	const known = KNOWN_SOURCE_LABELS[source];
	if (known) return known;
	return source
		.replace(/[_-]+/g, ' ')
		.trim()
		.replace(/\s+/g, ' ')
		.replace(/(^|\s)(\w)/g, (_match, separator: string, letter: string) => separator + letter.toUpperCase());
}

export const SENTIMENT_LABELS: Record<string, string> = {
	positive: 'Positivo',
	negative: 'Negativo',
	neutral: 'Neutro',
	null: 'Sin clasificar'
};

export function sentimentLabel(value: string | null): string {
	return SENTIMENT_LABELS[String(value)] ?? String(value);
}

/** Badge palette: green positive, red negative, gray neutral, outline unclassified. */
export function sentimentBadgeClass(value: string | null): string {
	switch (value) {
		case 'positive':
			return 'bg-green-50 text-green-700 ring-green-600/20';
		case 'negative':
			return 'bg-red-50 text-red-700 ring-red-600/20';
		case 'neutral':
			return 'bg-slate-100 text-slate-600 ring-slate-500/20';
		default:
			return 'bg-white text-slate-500 ring-slate-300';
	}
}

const PAD = (value: number) => String(value).padStart(2, '0');

/** UTC `YYYY-MM-DD HH:MM`; the raw string when unparseable, '—' when absent. */
export function formatUtcDateTime(value: string | null | undefined): string {
	if (!value) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	return (
		`${date.getUTCFullYear()}-${PAD(date.getUTCMonth() + 1)}-${PAD(date.getUTCDate())}` +
		` ${PAD(date.getUTCHours())}:${PAD(date.getUTCMinutes())} UTC`
	);
}

const dayFormatter = new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', timeZone: 'UTC' });

/** `2026-10-08` → `8 oct`, for chart axes (UTC, never shifted a day). */
export function formatDayLabel(isoDate: string): string {
	const date = new Date(`${isoDate}T00:00:00Z`);
	return Number.isNaN(date.getTime()) ? isoDate : dayFormatter.format(date);
}

export function formatScore(value: number | null): string {
	return value === null ? '' : value.toFixed(2);
}
