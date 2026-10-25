/**
 * Typed client for the media-monitor REST API.
 *
 * Every call runs server side (SvelteKit load functions and form actions):
 * the API has no CORS configuration, so the browser never talks to it
 * directly. The base URL comes from API_BASE_URL with the documented
 * development default http://localhost:8000.
 */

const DEFAULT_API_BASE_URL = "http://localhost:8000";

/** Resolved API base URL (no trailing slash). */
function apiBaseUrl(): string {
  const fromEnv =
    typeof process !== "undefined" ? process.env?.API_BASE_URL : undefined;
  const base = fromEnv?.trim() || DEFAULT_API_BASE_URL;
  return base.replace(/\/+$/, "");
}

/** Error raised for non-2xx API responses or unreachable backends. */
export class ApiError extends Error {
  readonly status: number;
  /** Raw `detail` payload: string on 4xx, array of issues on 422. */
  readonly detail: unknown;

  constructor(status: number, message: string, detail: unknown = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/* ---------------------------------- types --------------------------------- */

/** Sentiment label; rows without classification carry null. */
type Sentiment = "positive" | "negative" | "neutral";
/** `none` is the explicit unclassified filter on GET /api/mentions. */
export type SentimentFilter = Sentiment | "none";

/**
 * Source tag as stored by the backend (news_rss, gdelt, x_twitter, ...).
 * The set is open: new sources must render in the UI without changes here.
 */
type MentionSource = string;

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
  /** F2c one-paragraph enrichment; null until the mention is enriched. */
  summary: string | null;
  reach: number | null;
  /** One row per classifier; independent axis from sentiment. */
  classifications: Classification[];
  /** F3 persons linked via mention_persons; absent on stub payloads. */
  persons?: PersonRef[];
  /** Canonical event cluster; absent on stub payloads. */
  event_id?: number | null;
  event_title?: string | null;
}

/** Person chip on a mention card: id for the detail link, name for display. */
interface PersonRef {
  id: number;
  name: string;
}

/** One classifier's stored label for a mention. */
interface Classification {
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
  /** Outlet (URL host) filter, e.g. www.e-consulta.com; www-insensitive. */
  medium?: string;
  limit?: number;
  offset?: number;
}

export type KeywordLanguage = "es" | "en" | "other";

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

interface DailyVolumePoint {
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
  /** Mention counts per outlet (URL host): the feed «Medios» facet. */
  by_medium: Record<string, number>;
  /** Distinct outlets with ≥1 news mention («Medios con noticias» stat). */
  news_medium_count: number;
  last_24h: number;
  last_7d: number;
  /** 30 ascending daily buckets, zero-filled. */
  daily_volume: DailyVolumePoint[];
  /** One block per registered classifier (political v1). */
  classifications: ClassifierBreakdown[];
}

/** Aggregates for one classifier: total rows and count per label. */
interface ClassifierBreakdown {
  classifier: string;
  total_classified: number;
  breakdown: Record<string, number>;
}

/* --------------------------------- settings -------------------------------- */

type AiProvider = "local" | "openai";

/** X mention source: free Google News index or a paid provider API. */
export type XMode = "free" | "paid";

/** One monitored public Facebook page (mirrors FacebookPageTarget). */
interface FacebookPage {
  /** Numeric id or slug; the public wall is scraped, no tokens. */
  page_id: string;
  label: string;
}

export interface ClientSettings {
  id: number;
  client_id: number;
  client_name: string;
  timezone: string;
  retention_days: number;
  /** Daily digest cut hours (0..23, ascending); legacy digest_hour = first. */
  digest_hours: number[];
  /** Report recipient and watchlist principal (vigilancia F7); null = none. */
  digest_focus_person_id: number | null;
  /** F7: extra person ids under vigilance; the focus person is principal. */
  watchlist: number[];
  /** Worker per-cycle caps (1..1000; backend validates the range). */
  enrich_max_per_cycle: number;
  fetch_max_per_cycle: number;
  gdelt_enabled: boolean;
  facebook_pages: FacebookPage[];
  rss_feeds: string[];
  /** Enabled scrapers (keys of the backend SCRAPER_REGISTRY). */
  scrapers: string[];
  ai_provider: AiProvider;
  ai_api_key: string | null;
  ai_base_url: string | null;
  ai_model: string | null;
  ai_model_fast: string | null;
  /** Paid-mode X source; see x-mode-settings. */
  x_mode: XMode;
  /** Always "" on the wire: the API masks the stored key. */
  x_api_key: string;
  /** The only key signal: whether a key is stored. */
  x_api_key_set: boolean;
  /** ISO datetime of the last update. */
  updated_at: string;
}

/** Partial update: absent keys keep the stored value, empty strings clear optionals. */
export interface ClientSettingsInput {
  client_name?: string;
  timezone?: string;
  retention_days?: number;
  digest_hours?: number[];
  /** null clears the focus person; absent keeps the stored value. */
  digest_focus_person_id?: number | null;
  /** F7 vigilancia list; absent keeps the stored value. */
  watchlist?: number[];
  enrich_max_per_cycle?: number;
  fetch_max_per_cycle?: number;
  gdelt_enabled?: boolean;
  facebook_pages?: FacebookPage[];
  rss_feeds?: string[];
  scrapers?: string[];
  ai_provider?: AiProvider;
  ai_api_key?: string | null;
  ai_base_url?: string | null;
  ai_model?: string | null;
  ai_model_fast?: string | null;
  x_mode?: XMode;
  /** Non-empty stores the key; ''/absent keeps the stored one. */
  x_api_key?: string;
}

/** Result of POST /api/settings/test-ai (always answers, ok flags success). */
export interface AiProbeResult {
  ok: boolean;
  engine: string;
  model: string | null;
  latency_ms: number | null;
  label: string | null;
  error: string | null;
  /** Digest-narrative path probe; null for local providers. */
  narrative: AiNarrativeProbeResult | null;
}

export interface AiNarrativeProbeResult {
  ok: boolean;
  /** 'supported' | 'unsupported' | null. */
  json_schema: string | null;
  latency_ms: number | null;
  /** Schema-attempt failure detail when unsupported. */
  detail: string | null;
  error: string | null;
}

export interface AiProbeInput {
  provider: AiProvider;
  api_key?: string | null;
  base_url?: string | null;
  model?: string | null;
}

/* --------------------------------- plumbing -------------------------------- */

type FetchLike = typeof fetch;

export interface RequestOptions {
  /** Override the base URL for this call (tests, tooling). */
  baseUrl?: string;
  /** Inject a fetch implementation; defaults to globalThis.fetch. */
  fetch?: FetchLike;
}

function buildQuery(
  params: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "") continue;
    search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

function resolveBaseUrl(explicit?: string): string {
  return (explicit?.trim() || apiBaseUrl()).replace(/\/+$/, "");
}

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) =>
      typeof item === "object" && item !== null && "msg" in item
        ? String(item.msg)
        : String(item),
    );
    const joined = parts.filter(Boolean).join("; ");
    if (joined) return joined;
  }
  if (detail !== null && detail !== undefined && typeof detail === "object") {
    const nested = (detail as { detail?: unknown }).detail;
    if (typeof nested === "string" && nested) return nested;
  }
  return fallback;
}

async function request<T>(
  path: string,
  init: RequestInit,
  options: RequestOptions = {},
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
    throw new ApiError(
      response.status,
      detailToMessage(detail, fallback),
      detail,
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function jsonInit(
  method: "POST" | "PATCH" | "PUT",
  body: unknown,
): RequestInit {
  return {
    method,
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  };
}

/* -------------------------------- endpoints -------------------------------- */

export async function listMentions(
  query: MentionQuery = {},
  options: RequestOptions = {},
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
    medium: query.medium,
    limit: query.limit,
    offset: query.offset,
  });
  return request<MentionPage>(`/api/mentions${qs}`, { method: "GET" }, options);
}

export function getStatsOverview(
  options: RequestOptions = {},
): Promise<StatsOverview> {
  return request<StatsOverview>(
    "/api/stats/overview",
    { method: "GET" },
    options,
  );
}

/** One tone bucket of GET /stats/day (same shape as ToneCounts). */
export interface StatsDayToneBucket {
  positive: number;
  negative: number;
  neutral: number;
  unclassified: number;
  total: number;
}

/** GET /stats/day: home-page aggregates for one local day (home-digest-v2). */
export interface StatsDay {
  date: string;
  timezone: string;
  tones: {
    media: StatsDayToneBucket;
    social: StatsDayToneBucket;
    field: StatsDayToneBucket;
  };
  /** Mentions per keyword inside the day window (active + inactive). */
  keywords: { id: number; text: string; count: number }[];
}

/** Day aggregates for the home: local-day window, tone split, keyword hits. */
export function getDayStats(
  day: string,
  options: RequestOptions = {},
): Promise<StatsDay> {
  return request<StatsDay>(
    `/api/stats/day?date=${encodeURIComponent(day)}`,
    { method: "GET" },
    options,
  );
}

export function listKeywords(options: RequestOptions = {}): Promise<Keyword[]> {
  return request<Keyword[]>("/api/keywords", { method: "GET" }, options);
}

export function createKeyword(
  input: KeywordInput,
  options: RequestOptions = {},
): Promise<Keyword> {
  return request<Keyword>("/api/keywords", jsonInit("POST", input), options);
}

export function updateKeyword(
  id: number,
  patch: KeywordPatch,
  options: RequestOptions = {},
): Promise<Keyword> {
  return request<Keyword>(
    `/api/keywords/${id}`,
    jsonInit("PATCH", patch),
    options,
  );
}

export async function deleteKeyword(
  id: number,
  options: RequestOptions = {},
): Promise<void> {
  await request<void>(`/api/keywords/${id}`, { method: "DELETE" }, options);
}

/* --------------------------------- settings -------------------------------- */

export function getClientSettings(
  options: RequestOptions = {},
): Promise<ClientSettings> {
  return request<ClientSettings>("/api/settings", { method: "GET" }, options);
}

export function updateClientSettings(
  input: ClientSettingsInput,
  options: RequestOptions = {},
): Promise<ClientSettings> {
  return request<ClientSettings>(
    "/api/settings",
    jsonInit("PUT", input),
    options,
  );
}

/** A scrapable site without RSS, as exposed by the ingest registry. */
export interface AvailableScraper {
  name: string;
  base_url: string;
}

export function listAvailableScrapers(
  options: RequestOptions = {},
): Promise<AvailableScraper[]> {
  return request<AvailableScraper[]>(
    "/api/clients/1/scrapers/available",
    { method: "GET" },
    options,
  );
}

export function testAi(
  input: AiProbeInput,
  options: RequestOptions = {},
): Promise<AiProbeResult> {
  return request<AiProbeResult>(
    "/api/settings/test-ai",
    jsonInit("POST", input),
    options,
  );
}

/* ----------------------------- saved searches ----------------------------- */

/** One persisted monitoring query (social-listening core). */
export interface SavedSearch {
  id: number;
  client_id: number;
  name: string;
  /** Case-insensitive substring probe over title/content. */
  query: string;
  /** Empty array = every source. */
  sources: string[];
  classifier: string | null;
  label: string | null;
  range_days: number;
  is_active: boolean;
  created_at: string;
}

export interface SavedSearchInput {
  name: string;
  query: string;
  sources?: string[];
  classifier?: string | null;
  label?: string | null;
  range_days?: number;
  is_active?: boolean;
}

export interface SavedSearchPatch {
  name?: string;
  query?: string;
  sources?: string[];
  classifier?: string | null;
  label?: string | null;
  range_days?: number;
  is_active?: boolean;
}

export interface SpikeEvent {
  id: number;
  saved_search_id: number;
  saved_search_name: string;
  window_start: string;
  window_end: string;
  count: number;
  zscore: number;
  summary: string | null;
  summary_created_at: string | null;
}

export function listSavedSearches(
  options: RequestOptions = {},
): Promise<SavedSearch[]> {
  return request<SavedSearch[]>(
    "/api/clients/1/saved-searches",
    { method: "GET" },
    options,
  );
}

/** Which ingest sources have credentials/config: an ingest cycle would build their adapter. */
export async function getSourceReadiness(
  options: RequestOptions = {},
): Promise<Record<string, boolean>> {
  return request<Record<string, boolean>>(
    "/api/clients/1/source-readiness",
    { method: "GET" },
    options,
  );
}

export function createSavedSearch(
  input: SavedSearchInput,
  options: RequestOptions = {},
): Promise<SavedSearch> {
  return request<SavedSearch>(
    "/api/clients/1/saved-searches",
    jsonInit("POST", input),
    options,
  );
}

export function updateSavedSearch(
  id: number,
  patch: SavedSearchPatch,
  options: RequestOptions = {},
): Promise<SavedSearch> {
  return request<SavedSearch>(
    `/api/clients/1/saved-searches/${id}`,
    jsonInit("PATCH", patch),
    options,
  );
}

export async function deleteSavedSearch(
  id: number,
  options: RequestOptions = {},
): Promise<void> {
  await request<void>(
    `/api/clients/1/saved-searches/${id}`,
    { method: "DELETE" },
    options,
  );
}

export function listSpikes(
  query: { days?: number; limit?: number } = {},
  options: RequestOptions = {},
): Promise<SpikeEvent[]> {
  const qs = buildQuery({ days: query.days, limit: query.limit });
  return request<SpikeEvent[]>(
    `/api/clients/1/spikes${qs}`,
    { method: "GET" },
    options,
  );
}

/* ---------------------------------- persons -------------------------------- */

/** Person row with its denormalized mention count (list view). */
export interface PersonSummary {
  id: number;
  name: string;
  name_key: string;
  role: string | null;
  org: string | null;
  aliases: string[];
  first_seen_at: string;
  last_seen_at: string;
  mention_count: number;
}

/** One mention of the person: quote, source and context (F3 exit gate). */
interface PersonTimelineItem {
  mention_id: number;
  title: string | null;
  url: string;
  source: MentionSource;
  published_at: string | null;
  ingested_at: string;
  sentiment: Sentiment | null;
  /** Role the person held in THIS mention, per the enrichment. */
  role: string | null;
  org: string | null;
  /** Surrounding snippet of the mention, when the linker captured one. */
  context: string | null;
  event_id: number | null;
  event_title: string | null;
  political_label: string | null;
}

export interface PersonDetail extends PersonSummary {
  timeline: PersonTimelineItem[];
}

export function listPersons(
  query: {
    sort?: "mentions" | "recent";
    q?: string;
    limit?: number;
    offset?: number;
    since?: string;
    until?: string;
  } = {},
  options: RequestOptions = {},
): Promise<PersonSummary[]> {
  const qs = buildQuery({
    sort: query.sort,
    q: query.q,
    limit: query.limit,
    offset: query.offset,
    since: query.since,
    until: query.until,
  });
  return request<PersonSummary[]>(
    `/api/clients/1/persons${qs}`,
    { method: "GET" },
    options,
  );
}

export function getPerson(
  id: number,
  options: RequestOptions = {},
): Promise<PersonDetail> {
  return request<PersonDetail>(
    `/api/clients/1/persons/${id}`,
    { method: "GET" },
    options,
  );
}

/* ----------------------------------- events -------------------------------- */

/** Canonical event row: aggregated cluster, no mention drill-down. */
export interface EventSummary {
  id: number;
  title: string;
  mention_count: number;
  source_count: number;
  /** LLM synthesis over member summaries; the title while a lone mention. */
  summary: string | null;
  /** ISO datetimes in UTC. */
  first_seen_at: string;
  last_seen_at: string;
}

/** Mention stub inside an event detail: enough to rank and link out. */
interface EventMention {
  id: number;
  source: MentionSource;
  url: string;
  title: string | null;
  sentiment: Sentiment | null;
  published_at: string | null;
}

/** Event detail: the aggregate plus its corroborating mentions, reach-ranked. */
export interface EventDetail extends EventSummary {
  mentions: EventMention[];
}

/** Per-source coverage slice of one event. */
interface EventCoverageRow {
  source: MentionSource;
  n_mentions: number;
  outlets: number;
}

/** Which outlets covered an event and how many times each did. */
export interface EventCoverage {
  event_id: number;
  mention_count: number;
  outlet_count: number;
  by_source: EventCoverageRow[];
}

export function listEvents(
  query: { limit?: number; offset?: number; min_mentions?: number } = {},
  options: RequestOptions = {},
): Promise<EventSummary[]> {
  const qs = buildQuery({
    limit: query.limit,
    offset: query.offset,
    min_mentions: query.min_mentions,
  });
  return request<EventSummary[]>(
    `/api/clients/1/events${qs}`,
    { method: "GET" },
    options,
  );
}

export function getEvent(
  eventId: number,
  options: RequestOptions = {},
): Promise<EventDetail> {
  return request<EventDetail>(
    `/api/clients/1/events/${eventId}`,
    { method: "GET" },
    options,
  );
}

export function getEventCoverage(
  eventId: number,
  options: RequestOptions = {},
): Promise<EventCoverage> {
  return request<EventCoverage>(
    `/api/clients/1/events/${eventId}/coverage`,
    { method: "GET" },
    options,
  );
}

/* ------------------------------- ask (F4) --------------------------------- */

interface AskCitation {
  mention_id: number;
  title: string | null;
  url: string;
  source: MentionSource;
  published_at: string;
  sentiment: Sentiment | null;
}

export interface AskResult {
  answer: string;
  citations: AskCitation[];
  person: { id: number; name: string } | null;
  matched_mentions: number;
}

/** One-shot natural-language question over the corpus; cited answer. */
export function askCorpus(
  question: string,
  options: RequestOptions = {},
): Promise<AskResult> {
  return request<AskResult>(
    "/api/clients/1/ask",
    jsonInit("POST", { question }),
    options,
  );
}

/* ------------------------------- daily summaries --------------------------- */

/** One source citation inside a digest news item. */
interface DigestSourceRef {
  source: string;
  url: string;
  title?: string | null;
}

/** A digest news item: one canonical event (or loose mention) plus narrative. */
export interface DigestNewsItem {
  event_id: number | null;
  title: string | null;
  /** LLM/heuristic synthesis; grounded on the event facts. */
  summary?: string | null;
  /** Canonical topic key v2 (see format.topicLabel). */
  topic?: string | null;
  sources: DigestSourceRef[];
  /** alta | media | baja — rule-based, never LLM-authored. */
  confidence?: string;
  /** LLM one-liner justifying the confidence («fuente oficial directa»). */
  confidence_note?: string | null;
  /** Local-day stamp of the latest mention («22 oct.»); deterministic. */
  when_label?: string | null;
  /** The event circulated in a previous edition; cover as reiteration. */
  repeat?: boolean;
  person_ids?: number[];
  why_it_matters?: string | null;
}

interface DigestPersonItem {
  person_id: number;
  name: string;
  role?: string | null;
  org?: string | null;
  mention_count: number;
  fact?: string | null;
}

/** Structured sections of the editorial daily digest (schema 2). */
export interface DailySummaryContent {
  schema?: number;
  date?: string;
  timezone?: string;
  window?: { from?: string; to?: string };
  coverage?: {
    total?: number;
    by_source?: Record<string, number>;
    by_topic?: Record<string, number>;
    gaps?: string[];
  };
  noticias?: DigestNewsItem[];
  /** Agenda v2: LLM-authored upcoming items (home-digest-v2). */
  agenda?: { when: string; title: string; status?: string; source?: string }[];
  /**
   * Legacy rows may still carry a `rectora` key in their stored JSON; the
   * section was removed 25/oct and the key is ignored at render time.
   */
  redes?: Record<
    string,
    {
      count: number;
      note?: string;
      /** Per-account follow-ups (LLM); absent on legacy rows. */
      cuentas?: { cuenta: string; nota?: string }[];
    }
  >;
  personas?: DigestPersonItem[];
  pendientes?: string[];
  /** Active keywords with zero mentions: the «sin novedades» themes. */
  temas_sin_nota?: string[];
  /** Plain-text render of the whole digest, kept for the RAG chat. */
  plain_text?: string;
  /** digest-brief-v3 esqueleto (PR2). Absent on legacy v2 rows. */
  brief?: DigestBrief;
  /** Evidence cards, index-aligned with ``noticias``. */
  tarjetas?: DigestTarjeta[];
  /** Field reports captured in the window; ``estado`` carries the label. */
  campo?: DigestCampoEntry[];
}

/** One brief pick: the tarjeta index it references, never new data. */
export interface DigestAfectacion {
	quien?: string[];
	trayectoria?: string;
	ventana?: { cuando: string; titulo: string };
}

export interface DigestBriefSeleccion {
	index: number;
	categoria: 'decision' | 'riesgo' | 'ruido' | 'a_favor';
	razon?: string | null;
	afectacion?: DigestAfectacion;
}

/** F7: one vigilance line over a watched person's negative. */
export interface DigestVigilanciaEntry {
	persona: string;
	nota?: string | null;
	fecha: string;
	afectacion?: DigestAfectacion;
}

/** The v3 brief: fixed sections, CODE-built; the LLM only picks and writes prose. */
export interface DigestBrief {
	headline?: string | null;
	/** v3 brief delta: typed rows {titulo, giro} or legacy composed strings. */
	delta?: Array<string | { titulo: string; giro: string | null }>;
	decisiones?: DigestBriefSeleccion[];
	/** F5 risk bucket: negative-dominant cards, floor-filled post-pase. */
	riesgos?: DigestBriefSeleccion[];
	ruido?: DigestBriefSeleccion[];
	a_favor?: DigestBriefSeleccion[];
	fechas?: DigestBriefFecha[];
	/** F7 vigilance lines; absent when no watched person qualifies. */
	vigilancia?: DigestVigilanciaEntry[];
	/** F3: pre-card discard counters; absent when nothing was discarded. */
	descarte?: DigestDescarte;
}

/** Pre-card discard: cosmetic updates + stories merged into twins. */
export interface DigestDescarte {
  cosmeticas?: number;
  fundadas?: number;
}

/** A deadline the brief surfaces; ``estado`` is caducada | proxima. */
export interface DigestBriefFecha {
  title?: string | null;
  when?: string | null;
  estado?: string | null;
  /** ISO date the label was parsed to. */
  fecha?: string | null;
}

/** Evidence card for one digest story; mirrors the aligned noticia. */
export interface DigestTarjeta {
  titulo?: string | null;
  hecho?: string | null;
  por_que?: string | null;
  fuentes?: string[];
  tono?: string | null;
  repeat?: boolean;
  angulo_nuevo?: string | null;
}

/** One field report of the day, with its workflow estado. */
export interface DigestCampoEntry {
  titulo?: string | null;
  contenido?: string | null;
  lugar?: string | null;
  cuando?: string | null;
  estado?: string | null;
}

type SummaryMode = "heuristic" | "llm";

export interface DailySummary {
  id: number;
  client_id: number;
  /** ISO date (YYYY-MM-DD). */
  summary_date: string;
  content: DailySummaryContent;
  narrative: string;
  mode: SummaryMode;
  created_at: string;
  updated_at: string;
}

/** History entry: one stored day and the generator that produced it. */
export interface SummaryDayRef {
  summary_date: string;
  mode: SummaryMode;
}

export function getDailySummary(
  day: string,
  options: RequestOptions = {},
): Promise<DailySummary | null> {
  return request<DailySummary | null>(
    `/api/clients/1/summaries/${day}`,
    { method: "GET" },
    options,
  );
}

export function listSummaryDays(
  options: RequestOptions = {},
): Promise<SummaryDayRef[]> {
  return request<SummaryDayRef[]>(
    "/api/clients/1/summaries",
    { method: "GET" },
    options,
  );
}

/* ------------------------- narrative revisions ---------------------------- */

/** One stored narrative revision (build history, append-only). */
export interface SummaryRevision {
  seq: number;
  summary_date: string;
  narrative: string;
  mode: SummaryMode;
  created_at: string;
}

/** Index row: a day with stored revisions and how many. */
export interface SummaryRevisionDay {
  summary_date: string;
  count: number;
  last_at: string;
}

export function listSummaryRevisionDays(
  options: RequestOptions = {},
): Promise<SummaryRevisionDay[]> {
  return request<SummaryRevisionDay[]>(
    "/api/clients/1/summary-revisions",
    { method: "GET" },
    options,
  );
}

export function listSummaryRevisions(
  day: string,
  options: RequestOptions = {},
): Promise<SummaryRevision[]> {
  return request<SummaryRevision[]>(
    `/api/clients/1/summary-revisions/${day}`,
    { method: "GET" },
    options,
  );
}

export function restoreSummaryRevision(
  day: string,
  seq: number,
  options: RequestOptions = {},
): Promise<DailySummary> {
  return request<DailySummary>(
    "/api/clients/1/summary-revisions/restore",
    jsonInit("POST", { day, seq }),
    options,
  );
}

/** Builds (or regenerates) the summary; no date = today in the client tz. */
export function generateDailySummary(
  day?: string | null,
  options: RequestOptions = {},
): Promise<DailySummary> {
  return request<DailySummary>(
    "/api/clients/1/summaries/generate",
    jsonInit("POST", { date: day ?? null }),
    options,
  );
}

/* --------------------------------- agenda --------------------------------- */

/** Agenda entry (feature agenda-page): manual activity/deadline rows. */
export interface AgendaItem {
  id: number;
  client_id: number;
  title: string;
  kind: "activity" | "deadline";
  /** ISO date; null = «Sin fecha completa». */
  event_date: string | null;
  /** Source's partial date text («27 oct.»), kept for display. */
  date_label: string | null;
  time_label: string | null;
  location: string | null;
  source: string | null;
  url: string | null;
  notes: string | null;
  created_at: string;
}

export interface AgendaItemInput {
  title: string;
  kind?: "activity" | "deadline";
  event_date?: string | null;
  date_label?: string | null;
  time_label?: string | null;
  location?: string | null;
  source?: string | null;
  url?: string | null;
  notes?: string | null;
}

export function listAgendaItems(
  options: RequestOptions = {},
): Promise<AgendaItem[]> {
  return request<AgendaItem[]>(
    "/api/clients/1/agenda-items",
    { method: "GET" },
    options,
  );
}

export function createAgendaItem(
  input: AgendaItemInput,
  options: RequestOptions = {},
): Promise<AgendaItem> {
  return request<AgendaItem>(
    "/api/clients/1/agenda-items",
    jsonInit("POST", input),
    options,
  );
}

export function patchAgendaItem(
  id: number,
  patch: Partial<AgendaItemInput>,
  options: RequestOptions = {},
): Promise<AgendaItem> {
  return request<AgendaItem>(
    `/api/clients/1/agenda-items/${id}`,
    jsonInit("PATCH", patch),
    options,
  );
}

export function deleteAgendaItem(
  id: number,
  options: RequestOptions = {},
): Promise<void> {
  return request<void>(
    `/api/clients/1/agenda-items/${id}`,
    { method: "DELETE" },
    options,
  );
}

/* ----------------------------- field reports ----------------------------- */

/** One field report (the human channel) as the admin queue consumes it. */
export interface FieldReportRecord {
  id: number;
  status: "draft" | "review" | "published" | "rejected";
  operator_id: number | null;
  title: string | null;
  content: string | null;
  place: string | null;
  happened_at: string | null;
  review_note: string | null;
  /** LLM suggestions; null until the enrichment pass runs. */
  enrichment: {
    suggested_title?: string | null;
    summary?: string | null;
    tone?: string | null;
    duplicate?: boolean;
  } | null;
  mention_id: number | null;
  created_at: string | null;
  published_at: string | null;
}

export function listFieldReports(
  status?: "draft" | "review" | "published" | "rejected",
  options: RequestOptions = {},
): Promise<{ items: FieldReportRecord[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return request<{ items: FieldReportRecord[] }>(
    `/api/field-reports${qs}`,
    { method: "GET" },
    options,
  );
}

export function approveFieldReport(
  id: number,
  options: RequestOptions = {},
): Promise<FieldReportRecord> {
  return request<FieldReportRecord>(
    `/api/field-reports/${id}/approve`,
    { method: "POST" },
    options,
  );
}

export function rejectFieldReport(
  id: number,
  note: string | null,
  options: RequestOptions = {},
): Promise<FieldReportRecord> {
  return request<FieldReportRecord>(
    `/api/field-reports/${id}/reject`,
    jsonInit("POST", { note }),
    options,
  );
}

export function updateFieldReport(
  id: number,
  patch: Partial<Pick<FieldReportRecord, "title" | "content" | "place">>,
  options: RequestOptions = {},
): Promise<FieldReportRecord> {
  return request<FieldReportRecord>(
    `/api/field-reports/${id}`,
    jsonInit("PATCH", patch),
    options,
  );
}

export interface FieldOperatorRecord {
  id: number;
  display_name: string;
  telegram_user_id: number | null;
  phone: string | null;
  active: boolean;
  invited_at: string | null;
  accepted_at: string | null;
}

export function listFieldOperators(options: RequestOptions = {}): Promise<{
  items: FieldOperatorRecord[];
}> {
  return request<{ items: FieldOperatorRecord[] }>(
    "/api/field-operators",
    { method: "GET" },
    options,
  );
}

export function activateFieldOperator(
  id: number,
  options: RequestOptions = {},
): Promise<{ id: number; active: boolean }> {
  return request(
    `/api/field-operators/${id}/activate`,
    { method: "POST" },
    options,
  );
}

export function deactivateFieldOperator(
  id: number,
  options: RequestOptions = {},
): Promise<{ id: number; active: boolean }> {
  return request(
    `/api/field-operators/${id}/deactivate`,
    { method: "POST" },
    options,
  );
}

export function createFieldOperator(
  input: {
    display_name: string;
    phone: string;
    telegram_user_id?: number | null;
  },
  options: RequestOptions = {},
): Promise<FieldOperatorRecord> {
  return request<FieldOperatorRecord>(
    "/api/field-operators",
    jsonInit("POST", input),
    options,
  );
}

export function inviteFieldOperator(
  id: number,
  options: RequestOptions = {},
): Promise<{ id: number; token: string; link: string | null }> {
  return request(
    `/api/field-operators/${id}/invite`,
    { method: "POST" },
    options,
  );
}
