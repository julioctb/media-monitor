/**
 * Typed client for the media-monitor REST API.
 *
 * Every call runs server side (SvelteKit load functions and form actions):
 * the API has no CORS configuration, so the browser never talks to it
 * directly. The base URL comes from API_BASE_URL with the documented
 * development default http://localhost:8000.
 */

const DEFAULT_API_BASE_URL = 'http://localhost:8000';

/** Resolved API base URL (no trailing slash). */
export function apiBaseUrl(): string {
	const fromEnv = typeof process !== 'undefined' ? process.env?.API_BASE_URL : undefined;
	const base = fromEnv?.trim() || DEFAULT_API_BASE_URL;
	return base.replace(/\/+$/, '');
}

/** Error raised for non-2xx API responses or unreachable backends. */
export class ApiError extends Error {
	readonly status: number;
	/** Raw `detail` payload: string on 4xx, array of issues on 422. */
	readonly detail: unknown;

	constructor(status: number, message: string, detail: unknown = null) {
		super(message);
		this.name = 'ApiError';
		this.status = status;
		this.detail = detail;
	}
}

/* ---------------------------------- types --------------------------------- */

/** Sentiment label; rows without classification carry null. */
export type Sentiment = 'positive' | 'negative' | 'neutral';
/** `none` is the explicit unclassified filter on GET /api/mentions. */
export type SentimentFilter = Sentiment | 'none';

/**
 * Source tag as stored by the backend (news_rss, gdelt, x_twitter, ...).
 * The set is open: new sources must render in the UI without changes here.
 */
export type MentionSource = string;

export interface Mention {
	id: number;
	keyword_id: number | null;
	source: MentionSource;
	external_id: string | null;
	url: string;
	title: string | null;
	content: string | null;
	author: string | null;
	lang: string | null;
	/** ISO datetime in UTC, or null when never published. */
	published_at: string | null;
	ingested_at: string;
	sentiment: Sentiment | null;
	sentiment_score: number | null;
	reach: number | null;
	/** One row per classifier; independent axis from sentiment. */
	classifications: Classification[];
}

/** One classifier's stored label for a mention. */
export interface Classification {
	classifier: string;
	label: string;
	score: number;
}

export interface MentionPage {
	items: Mention[];
	total: number;
}

export interface MentionQuery {
	source?: MentionSource;
	sentiment?: SentimentFilter;
	keyword_id?: number;
	/** Classification probe: rows carrying this classifier (+ label). */
	classifier?: string;
	label?: string;
	/** ISO datetime; the UI expands date-only values to UTC day bounds. */
	since?: string;
	until?: string;
	/** Substring search over title and content. */
	q?: string;
	limit?: number;
	offset?: number;
}

export type KeywordLanguage = 'es' | 'en';

export interface Keyword {
	id: number;
	text: string;
	language: KeywordLanguage;
	is_active: boolean;
	created_at: string;
}

export interface KeywordInput {
	text: string;
	language: KeywordLanguage;
}

export interface KeywordPatch {
	is_active?: boolean;
}

export type AlertDigest = 'instant' | 'daily' | 'weekly';

export interface AlertSettings {
	digest: AlertDigest;
	recipient_email: string | null;
	is_active: boolean;
}

export interface AlertSettingsInput {
	digest: AlertDigest;
	/** The API requires a valid address on every PUT. */
	recipient_email: string;
	is_active: boolean;
}

export interface DailyVolumePoint {
	/** ISO date of the UTC day bucket. */
	date: string;
	count: number;
}

export interface StatsOverview {
	total: number;
	/** Keys: positive | negative | neutral | null (unclassified bucket). */
	by_sentiment: Record<string, number>;
	/** Keys are source tags; open set, render generically. */
	by_source: Record<string, number>;
	last_24h: number;
	last_7d: number;
	/** 30 ascending daily buckets, zero-filled. */
	daily_volume: DailyVolumePoint[];
	/** One block per registered classifier (political v1). */
	classifications: ClassifierBreakdown[];
}

/** Aggregates for one classifier: total rows and count per label. */
export interface ClassifierBreakdown {
	classifier: string;
	total_classified: number;
	breakdown: Record<string, number>;
}

/* --------------------------------- settings -------------------------------- */

export type AiProvider = 'local' | 'openai';

/** One monitored Facebook page (mirrors FacebookPageCredentials). */
export interface FacebookPage {
	page_id: string;
	token: string;
	label: string;
}

export interface ClientSettings {
	id: number;
	client_id: number;
	client_name: string;
	timezone: string;
	retention_days: number;
	gdelt_enabled: boolean;
	facebook_pages: FacebookPage[];
	rss_feeds: string[];
	ai_provider: AiProvider;
	ai_api_key: string | null;
	ai_base_url: string | null;
	ai_model: string | null;
	ai_fallback_local: boolean;
	/** ISO datetime of the last update. */
	updated_at: string;
}

/** Partial update: absent keys keep the stored value, empty strings clear optionals. */
export interface ClientSettingsInput {
	client_name?: string;
	timezone?: string;
	retention_days?: number;
	gdelt_enabled?: boolean;
	facebook_pages?: FacebookPage[];
	rss_feeds?: string[];
	ai_provider?: AiProvider;
	ai_api_key?: string | null;
	ai_base_url?: string | null;
	ai_model?: string | null;
	ai_fallback_local?: boolean;
}

/** Result of POST /api/settings/test-facebook (always answers, ok flags success). */
export interface FacebookProbeResult {
	ok: boolean;
	error: string | null;
	name: string | null;
	link: string | null;
}

/** Result of POST /api/settings/test-ai (always answers, ok flags success). */
export interface AiProbeResult {
	ok: boolean;
	engine: string;
	model: string | null;
	latency_ms: number | null;
	label: string | null;
	error: string | null;
}

export interface FacebookProbeInput {
	page_id: string;
	token: string;
}

export interface AiProbeInput {
	provider: AiProvider;
	api_key?: string | null;
	base_url?: string | null;
	model?: string | null;
}

/* --------------------------------- plumbing -------------------------------- */

export type FetchLike = typeof fetch;

export interface RequestOptions {
	/** Override the base URL for this call (tests, tooling). */
	baseUrl?: string;
	/** Inject a fetch implementation; defaults to globalThis.fetch. */
	fetch?: FetchLike;
}

function buildQuery(params: Record<string, string | number | undefined>): string {
	const search = new URLSearchParams();
	for (const [key, value] of Object.entries(params)) {
		if (value === undefined || value === '') continue;
		search.set(key, String(value));
	}
	const qs = search.toString();
	return qs ? `?${qs}` : '';
}

function resolveBaseUrl(explicit?: string): string {
	return (explicit?.trim() || apiBaseUrl()).replace(/\/+$/, '');
}

function detailToMessage(detail: unknown, fallback: string): string {
	if (typeof detail === 'string' && detail.trim()) return detail;
	if (Array.isArray(detail)) {
		const parts = detail.map((item) =>
			typeof item === 'object' && item !== null && 'msg' in item ? String(item.msg) : String(item)
		);
		const joined = parts.filter(Boolean).join('; ');
		if (joined) return joined;
	}
	if (detail !== null && detail !== undefined && typeof detail === 'object') {
		const nested = (detail as { detail?: unknown }).detail;
		if (typeof nested === 'string' && nested) return nested;
	}
	return fallback;
}

async function request<T>(
	path: string,
	init: RequestInit,
	options: RequestOptions = {}
): Promise<T> {
	const doFetch = options.fetch ?? fetch;
	const url = `${resolveBaseUrl(options.baseUrl)}${path}`;

	let response: Response;
	try {
		response = await doFetch(url, init);
	} catch (cause) {
		const reason = cause instanceof Error ? cause.message : String(cause);
		throw new ApiError(0, `No se pudo contactar la API (${reason})`);
	}

	if (!response.ok) {
		let detail: unknown = null;
		const fallback = `La API respondió ${response.status}`;
		try {
			const body = (await response.json()) as { detail?: unknown } | null;
			detail = body?.detail ?? body ?? null;
		} catch {
			// Non-JSON error body: keep the generic message.
		}
		throw new ApiError(response.status, detailToMessage(detail, fallback), detail);
	}

	if (response.status === 204) {
		return undefined as T;
	}
	return (await response.json()) as T;
}

function jsonInit(method: 'POST' | 'PATCH' | 'PUT', body: unknown): RequestInit {
	return {
		method,
		headers: { 'content-type': 'application/json' },
		body: JSON.stringify(body)
	};
}

/* -------------------------------- endpoints -------------------------------- */

export async function listMentions(
	query: MentionQuery = {},
	options: RequestOptions = {}
): Promise<MentionPage> {
	const qs = buildQuery({
		source: query.source,
		sentiment: query.sentiment,
		keyword_id: query.keyword_id,
		classifier: query.classifier,
		label: query.label,
		since: query.since,
		until: query.until,
		q: query.q,
		limit: query.limit,
		offset: query.offset
	});
	return request<MentionPage>(`/api/mentions${qs}`, { method: 'GET' }, options);
}

export function getStatsOverview(options: RequestOptions = {}): Promise<StatsOverview> {
	return request<StatsOverview>('/api/stats/overview', { method: 'GET' }, options);
}

export function listKeywords(options: RequestOptions = {}): Promise<Keyword[]> {
	return request<Keyword[]>('/api/keywords', { method: 'GET' }, options);
}

export function createKeyword(input: KeywordInput, options: RequestOptions = {}): Promise<Keyword> {
	return request<Keyword>('/api/keywords', jsonInit('POST', input), options);
}

export function updateKeyword(
	id: number,
	patch: KeywordPatch,
	options: RequestOptions = {}
): Promise<Keyword> {
	return request<Keyword>(`/api/keywords/${id}`, jsonInit('PATCH', patch), options);
}

export async function deleteKeyword(id: number, options: RequestOptions = {}): Promise<void> {
	await request<void>(`/api/keywords/${id}`, { method: 'DELETE' }, options);
}

export function getAlertSettings(options: RequestOptions = {}): Promise<AlertSettings> {
	return request<AlertSettings>('/api/alerts/settings', { method: 'GET' }, options);
}

export function updateAlertSettings(
	input: AlertSettingsInput,
	options: RequestOptions = {}
): Promise<AlertSettings> {
	return request<AlertSettings>('/api/alerts/settings', jsonInit('PUT', input), options);
}

/* --------------------------------- settings -------------------------------- */

export function getClientSettings(options: RequestOptions = {}): Promise<ClientSettings> {
	return request<ClientSettings>('/api/settings', { method: 'GET' }, options);
}

export function updateClientSettings(
	input: ClientSettingsInput,
	options: RequestOptions = {}
): Promise<ClientSettings> {
	return request<ClientSettings>('/api/settings', jsonInit('PUT', input), options);
}

export function testFacebookPage(
	input: FacebookProbeInput,
	options: RequestOptions = {}
): Promise<FacebookProbeResult> {
	return request<FacebookProbeResult>('/api/settings/test-facebook', jsonInit('POST', input), options);
}

export function testAi(input: AiProbeInput, options: RequestOptions = {}): Promise<AiProbeResult> {
	return request<AiProbeResult>('/api/settings/test-ai', jsonInit('POST', input), options);
}
