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

const SENTIMENT_LABELS: Record<string, string> = {
	positive: 'Positivo',
	negative: 'Negativo',
	neutral: 'Neutro',
	null: 'Sin clasificar'
};

export function sentimentLabel(value: string | null): string {
	return SENTIMENT_LABELS[String(value)] ?? String(value);
}

/** Classification labels (open set; unknown labels fall through). */
const CLASSIFICATION_LABELS: Record<string, string> = {
	political: 'Política',
	not_political: 'No política',
	uncertain: 'Sin clasificar'
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


/**
 * Display timezone: client headquarters (America/Mexico_City, UTC-6 all
 * year — Mexico abolished DST in 2022). When multi-timezone clients land,
 * thread settings.timezone through the layout load instead.
 */
const DISPLAY_TIMEZONE = 'America/Mexico_City';

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

/** `2026-10-20T14:03` → `20 de octubre de 2026 - 14:03` (24h, hora local). */
export function formatDisplayDateTimeLong(value: string | null | undefined): string {
	if (!value) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	const fmt = new Intl.DateTimeFormat('es-MX', {
		timeZone: DISPLAY_TIMEZONE,
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		hour: '2-digit',
		minute: '2-digit',
		hour12: false
	});
	const parts = fmt.formatToParts(date).reduce<Record<string, string>>((acc, p) => {
		acc[p.type] = p.value;
		return acc;
	}, {});
	return `${parts.day} de ${parts.month} de ${parts.year} - ${parts.hour}:${parts.minute}`;
}

const dayFormatter = new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', timeZone: 'UTC' });

const longDateFormatter = new Intl.DateTimeFormat('es-MX', {
	timeZone: DISPLAY_TIMEZONE,
	day: 'numeric',
	month: 'long',
	year: 'numeric'
});

/** `2026-10-19T…` → `19 de octubre de 2026` (negative-news source line). */
export function formatDateLong(value: string | null | undefined): string {
	if (!value) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	return longDateFormatter.format(date);
}

/** `2026-10-19T06:24` → `19/10/2026 a las 06:24` (detalle-actor mockup). */
export function formatDisplayDateTimeAt(value: string | null | undefined): string {
	const base = formatDisplayDateTime(value);
	if (!base || base === '—') return base;
	const [date, time] = base.split(' ');
	return time ? `${date} a las ${time}` : base;
}

/** `2026-10-08` → `8 oct`, for chart axes (UTC, never shifted a day). */
export function formatDayLabel(isoDate: string): string {
	const date = new Date(`${isoDate}T00:00:00Z`);
	return Number.isNaN(date.getTime()) ? isoDate : dayFormatter.format(date);
}


const MONTHS_ES = [
	'enero',
	'febrero',
	'marzo',
	'abril',
	'mayo',
	'junio',
	'julio',
	'agosto',
	'septiembre',
	'octubre',
	'noviembre',
	'diciembre'
];

const WEEKDAYS_ES = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado'];

/**
 * `2026-10-19` → `Domingo 19 de octubre, 2026` (digest h1, mockup wording).
 * Non-date input falls through untouched. Computed in local time from the
 * date-only components so no timezone can shift the weekday.
 */
export function formatLongDate(isoDate: string): string {
	const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
	if (!match) return isoDate;
	const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
	if (Number.isNaN(date.getTime())) return isoDate;
	const weekday = WEEKDAYS_ES[date.getDay()];
	const capital = weekday.charAt(0).toUpperCase() + weekday.slice(1);
	return `${capital} ${date.getDate()} de ${MONTHS_ES[date.getMonth()]}, ${date.getFullYear()}`;
}

/** Lowercase, de-accented, punctuation-free token set for fuzzy comparisons. */
function contentTokens(text: string): Set<string> {
	return new Set(
		text
			.toLowerCase()
			.normalize('NFD')
			.replace(/[\u0300-\u036f]/g, '')
			.replace(/[^a-z0-9\s]/g, ' ')
			.split(/\s+/)
			.filter((t) => t.length > 2)
	);
}

/**
 * Chip label for the canonical-event link: the event title when it adds
 * information, or a plain call-to-action when it would just repeat the mention
 * title (the cluster title is inherited from its first mention, source
 * suffix included, so the two usually near-duplicate).
 */
export function eventChipLabel(mentionTitle: string | null, eventTitle: string): string {
	const mentionTokens = contentTokens(mentionTitle ?? '');
	const eventTokens = contentTokens(eventTitle);
	if (mentionTokens.size === 0 || eventTokens.size === 0) return `Evento: ${eventTitle}`;
	const overlap = [...eventTokens].filter((t) => mentionTokens.has(t)).length;
	const duplicated =
		overlap / eventTokens.size >= 0.8 || overlap / mentionTokens.size >= 0.8;
	return duplicated ? 'Ver evento' : `Evento: ${eventTitle}`;
}

/**
 * ISO date -> the day's [since, until] instants bounded in the display
 * timezone, as ISO strings with numeric offsets (the API compares
 * timestamptz, so the day edges must carry the zone, not Z).
 * The offset is sampled at local noon of the day: DST-safe by construction.
 */
export function zonedDayBounds(
	dayIso: string,
	timeZone: string = DISPLAY_TIMEZONE
): { since: string; until: string } {
	const noon = new Date(`${dayIso}T12:00:00Z`);
	const parts = new Intl.DateTimeFormat('en-US', {
		timeZone,
		hour12: false,
		year: 'numeric',
		month: '2-digit',
		day: '2-digit',
		hour: '2-digit',
		minute: '2-digit'
	})
		.formatToParts(noon)
		.reduce<Record<string, string>>((acc, part) => {
			acc[part.type] = part.value;
			return acc;
		}, {});
	const hour = parts.hour === '24' ? 0 : Number(parts.hour);
	const asUTC = Date.UTC(
		Number(parts.year),
		Number(parts.month) - 1,
		Number(parts.day),
		hour,
		Number(parts.minute)
	);
	const offsetMin = Math.round((asUTC - noon.getTime()) / 60000);
	const sign = offsetMin < 0 ? '-' : '+';
	const abs = Math.abs(offsetMin);
	const offset = `${sign}${String(Math.floor(abs / 60)).padStart(2, '0')}:${String(abs % 60).padStart(2, '0')}`;
	return { since: `${dayIso}T00:00:00${offset}`, until: `${dayIso}T23:59:59${offset}` };
}

/** HH:MM in the display timezone; raw string when unparseable, '—' when absent. */
export function formatDisplayTime(value: string | null | undefined): string {
	if (!value) return '—';
	const date = new Date(value);
	if (Number.isNaN(date.getTime())) return value;
	const parts = mexicoFormatter.formatToParts(date).reduce<Record<string, string>>((acc, part) => {
		acc[part.type] = part.value;
		return acc;
	}, {});
	return `${parts.hour}:${parts.minute}`;
}

/**
 * Next digest cut label («HH:00») after now, in the display timezone.
 * Cuts sit on the hour; past the last one the answer is tomorrow's first
 * (the stamp shows no date by design). null when the schedule is unknown.
 */
export function nextCutLabel(hours: number[] | undefined, now: Date): string | null {
	if (!hours || hours.length === 0) return null;
	const parts = new Intl.DateTimeFormat('en-US', {
		timeZone: DISPLAY_TIMEZONE,
		hour12: false,
		hour: '2-digit'
	}).formatToParts(now);
	const raw = parts.find((part) => part.type === 'hour')?.value ?? '0';
	const nowHour = Number(raw) % 24;
	const sorted = [...hours].sort((a, b) => a - b);
	const next = sorted.find((hour) => hour > nowHour) ?? sorted[0];
	return `${next}:00`;
}

/**
 * Digest prose cleaner: syndicated text (X posts above all) carries emojis,
 `t.co` links, `@url:` artifacts and @handles; the editorial detail renders
 paraphrase-friendly prose, never the raw post.
 */
const URL_RE = /(https?:\/\/|www\.)\S+/g;
const HANDLE_RE = /@[a-zA-Z0-9_.]+/g;
const EMOJI_RE =
	/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}\u{2B00}-\u{2BFF}\u{FE0F}\u{200D}]/gu;

export function cleanDigestText(text: string): string {
	return text
		.replace(URL_RE, '')
		.replace(/@url\s*:\s*/gi, '')
		.replace(HANDLE_RE, '')
		.replace(EMOJI_RE, '')
		.replace(/`/g, '')
		.replace(/\s{2,}/g, ' ')
		.trim();
}
