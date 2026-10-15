/**
 * Presentation helpers. Datetimes render in the client display timezone
 * (America/Mexico_City); source labels are derived generically because the
 * source set is open (the backend adds e.g. facebook_page without UI changes).
 */

/** Friendly names for known tags; unknown tags fall through to generic casing. */
const KNOWN_SOURCE_LABELS: Record<string, string> = {
	news_rss: 'News RSS',
	gdelt: 'GDELT',
	x_twitter: 'X (Twitter)',
	rss_custom: 'RSS propios'
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

/** Classification labels (open set; unknown labels fall through). */
const CLASSIFICATION_LABELS: Record<string, string> = {
	political: 'Política',
	not_political: 'No política'
};

export function classificationLabel(label: string): string {
	return CLASSIFICATION_LABELS[label] ?? label;
}

/** Topic labels v2 (classification-v2): keys mirror app.classifications.topics. */
const TOPIC_LABELS: Record<string, string> = {
	academic: 'Academia',
	infrastructure: 'Infraestructura',
	institutional: 'Institucional',
	students: 'Estudiantes',
	culture: 'Cultura',
	sports: 'Deportes',
	finance: 'Finanzas',
	government: 'Gobierno',
	health: 'Salud',
	// v1 labels kept for rows not yet re-classified.
	economy: 'Economía'
};

export function topicLabel(label: string): string {
	return TOPIC_LABELS[label] ?? label;
}

/** One hue per topic so a multi-label badge row scans instantly. */
const TOPIC_BADGE_CLASSES: Record<string, string> = {
	academic: 'bg-indigo-50 text-indigo-700 ring-indigo-600/20',
	infrastructure: 'bg-amber-50 text-amber-700 ring-amber-600/20',
	institutional: 'bg-slate-100 text-slate-600 ring-slate-500/20',
	students: 'bg-sky-50 text-sky-700 ring-sky-600/20',
	culture: 'bg-fuchsia-50 text-fuchsia-700 ring-fuchsia-600/20',
	sports: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
	finance: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20',
	government: 'bg-orange-50 text-orange-700 ring-orange-600/20',
	health: 'bg-teal-50 text-teal-700 ring-teal-600/20',
	// v1 legacy (rows not yet re-classified)
	economy: 'bg-amber-50 text-amber-700 ring-amber-600/20'
};

export function topicBadgeClass(label: string): string {
	return TOPIC_BADGE_CLASSES[label] ?? 'bg-slate-100 text-slate-500 ring-slate-400/20';
}

const PAD = (value: number) => String(value).padStart(2, '0');

/**
 * Display timezone: client headquarters (America/Mexico_City, UTC-6 all
 * year — Mexico abolished DST in 2022). When multi-timezone clients land,
 * thread settings.timezone through the layout load instead.
 */
export const DISPLAY_TIMEZONE = 'America/Mexico_City';

const mexicoFormatter = new Intl.DateTimeFormat('es-MX', {
	timeZone: DISPLAY_TIMEZONE,
	day: '2-digit',
	month: '2-digit',
	year: 'numeric',
	hour: '2-digit',
	minute: '2-digit',
	hour12: false
});

/** `dd/mm/aaaa HH:MM` in Mexico City time; raw string when unparseable, '—' when absent. */
export function formatDisplayDateTime(value: string | null | undefined): string {
	if (!value) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	const parts = mexicoFormatter.formatToParts(date).reduce<Record<string, string>>((acc, part) => {
		acc[part.type] = part.value;
		return acc;
	}, {});
	return `${parts.day}/${parts.month}/${parts.year} ${parts.hour}:${parts.minute}`;
}

const dayFormatter = new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', timeZone: 'UTC' });

/** `2026-10-08` → `8 oct`, for chart axes (UTC, never shifted a day). */
export function formatDayLabel(isoDate: string): string {
	const date = new Date(`${isoDate}T00:00:00Z`);
	return Number.isNaN(date.getTime()) ? isoDate : dayFormatter.format(date);
}

