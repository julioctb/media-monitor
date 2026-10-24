import { error, fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	ApiError,
	getClientSettings,
	listAvailableScrapers,
	listKeywords,
	listPersons,
	testAi,
	updateClientSettings
} from '$lib/api';
import type { AiNarrativeProbeResult } from '$lib/api';
import { normalizeFacebookPageRef } from '$lib/facebook-page';
import { handleKeywordCreate, handleKeywordDelete, handleKeywordToggle } from '$lib/keyword-actions';
import type { Actions, PageServerLoad } from './$types';

/** Uniform action result: every branch carries the same keys for the view. */
interface SettingsActionResult {
	action: 'save' | 'save-x' | 'test-ai';
	ok: boolean;
	/** Banner text on save; probe outcome/error on the test action. */
	message: string;
	engine: string | null;
	model: string | null;
	latency_ms: number | null;
	label: string | null;
	/** Digest-narrative probe; null for local providers / older backends. */
	narrative?: AiNarrativeProbeResult | null;
}

type ActionResultExtras = Partial<
	Pick<SettingsActionResult, 'engine' | 'model' | 'latency_ms' | 'label' | 'narrative'>
>;

/** Probe-shaped defaults so callers only pass the fields they know. */
function actionResult(
	action: SettingsActionResult['action'],
	ok: boolean,
	message: string,
	extras: ActionResultExtras = {}
): SettingsActionResult {
	return {
		engine: null,
		model: null,
		latency_ms: null,
		label: null,
		...extras,
		action,
		ok,
		message
	};
}

function failure(action: SettingsActionResult['action'], status: number, message: string) {
	return fail(status, actionResult(action, false, message));
}

function failureFrom(cause: unknown, action: SettingsActionResult['action'], fallback: string) {
	const status = errorStatus(cause, 502);
	const message = errorMessage(cause, fallback);
	return failure(action, status, message);
}

const SAVE_OK_MESSAGE = 'Configuración guardada.';
const X_SAVE_OK_MESSAGE = 'Configuración de X guardada.';

function text(form: FormData, key: string): string {
	const value = form.get(key);
	return typeof value === 'string' ? value.trim() : '';
}

/** '' normalizes to null: the API clears optional fields on null. */
function optionalText(form: FormData, key: string): string | null {
	const value = text(form, key);
	return value === '' ? null : value;
}

const DIGEST_HOUR_RE = /^\d{1,2}$/;
/** Backend bounds: ClientSettingsUpdate ge=1 le=1000 on both cycle caps. */
const CYCLE_CAP_RE = /^\d{1,4}$/;
const FOCUS_ID_RE = /^\d+$/;

/**
 * Per-cycle cap from a number input: 1..1000 or null when absent/invalid
 * (the caller turns null into a friendly 400).
 */
function readCycleCap(form: FormData, key: string): number | null {
	const raw = text(form, key);
	if (!CYCLE_CAP_RE.test(raw)) return null;
	const value = Number.parseInt(raw, 10);
	return value >= 1 && value <= 1000 ? value : null;
}

/**
 * Digest cut hours from the repeated `digest_hour` inputs: parsed, clamped
 * to 0..23, deduped. Returns null when the resulting list is empty or over
 * the 8-cut cap so the caller can surface a friendly error.
 */
function readDigestHours(form: FormData): number[] | null {
	const seen = new Set<number>();
	for (const entry of form.getAll('digest_hour')) {
		const raw = String(entry).trim();
		if (!DIGEST_HOUR_RE.test(raw)) continue;
		const hour = Number.parseInt(raw, 10);
		if (hour < 0 || hour > 23) continue;
		seen.add(hour);
	}
	const hours = [...seen].sort((a, b) => a - b);
	return hours.length >= 1 && hours.length <= 8 ? hours : null;
}

/** Zip the repeated row inputs by DOM order; normalize, dedupe, drop junk. */
function readFacebookPages(form: FormData): { page_id: string; label: string }[] {
	const urls = form.getAll('fb_url').map((value) => String(value));
	const labels = form.getAll('fb_label').map((value) => String(value));
	const pages: { page_id: string; label: string }[] = [];
	const seen = new Set<string>();
	for (let index = 0; index < urls.length; index += 1) {
		const page_id = normalizeFacebookPageRef(urls[index] ?? '');
		// Empty and unparseable rows drop silently; a repeated ref keeps its
		// first label.
		if (page_id === null || seen.has(page_id)) continue;
		seen.add(page_id);
		pages.push({ page_id, label: (labels[index] ?? '').trim() });
	}
	return pages;
}

export const load: PageServerLoad = async () => {
	try {
		// Best-effort: an unavailable registry must not block the page; the
		// card renders an empty state instead. Keywords feed the embedded
		// panel; a failure there degrades to an empty table.
		const [scrapersAvailable, keywords, persons] = await Promise.all([
			listAvailableScrapers().catch(() => []),
			listKeywords().catch(() => []),
			// Best-effort too: the focus select degrades to the none option.
			listPersons().catch(() => [])
		]);
		return { settings: await getClientSettings(), scrapersAvailable, keywords, persons };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudo cargar la configuración: ${detail}`);
	}
};

export const actions: Actions = {
	save: async ({ request }) => {
		const form = await request.formData();

		const retentionRaw = text(form, 'retention_days');
		const retention_days = Number.parseInt(retentionRaw, 10);
		if (retentionRaw === '' || Number.isNaN(retention_days)) {
			return failure('save', 400, 'Ingresa los días de retención: 0 desactiva el purge.');
		}

		const digest_hours = readDigestHours(form);
		if (digest_hours === null) {
			return failure(
				'save',
				400,
				'Configura entre 1 y 8 horarios de resumen, cada uno entre 0 y 23.'
			);
		}

		const enrich_max_per_cycle = readCycleCap(form, 'enrich_max_per_cycle');
		const fetch_max_per_cycle = readCycleCap(form, 'fetch_max_per_cycle');
		if (enrich_max_per_cycle === null || fetch_max_per_cycle === null) {
			return failure('save', 400, 'Configura los máximos por ciclo entre 1 y 1000.');
		}

		// '' = Sin persona focus -> null clears the stored id; anything else
		// must be a positive integer (the select only emits known ids).
		const focusRaw = text(form, 'digest_focus_person_id');
		let digest_focus_person_id: number | null = null;
		if (focusRaw !== '') {
			if (!FOCUS_ID_RE.test(focusRaw)) {
				return failure('save', 400, 'Persona focus inválida.');
			}
			digest_focus_person_id = Number.parseInt(focusRaw, 10);
		}

		try {
			// Full-object PUT: the API keeps server-side fields (id, client_id,
			// updated_at) and validates the rest, mirroring the stored row.
			await updateClientSettings({
				timezone: text(form, 'timezone'),
				retention_days,
				digest_hours,
				digest_focus_person_id,
				enrich_max_per_cycle,
				fetch_max_per_cycle,
				gdelt_enabled: form.get('gdelt_enabled') === '1',
				facebook_pages: readFacebookPages(form),
				rss_feeds: text(form, 'rss_feeds')
					.split('\n')
					.map((line) => line.trim())
					.filter((line) => line !== ''),
				scrapers: form.getAll('scrapers').map((value) => String(value)),
				ai_provider: form.get('ai_provider') === 'openai' ? 'openai' : 'local',
				ai_api_key: optionalText(form, 'ai_api_key'),
				ai_base_url: optionalText(form, 'ai_base_url'),
				ai_model: optionalText(form, 'ai_model')
			});
			return actionResult('save', true, SAVE_OK_MESSAGE);
		} catch (cause) {
			return failureFrom(cause, 'save', 'No se pudo guardar la configuración.');
		}
	},

	'test-ai': async ({ request }) => {
		const form = await request.formData();
		const provider = form.get('ai_provider') === 'openai' ? 'openai' : 'local';

		try {
			const probe = await testAi({
				provider,
				api_key: optionalText(form, 'ai_api_key'),
				base_url: optionalText(form, 'ai_base_url'),
				model: optionalText(form, 'ai_model')
			});
			return actionResult(
				'test-ai',
				probe.ok,
				probe.ok ? 'Conexión correcta.' : String(probe.error ?? 'Error desconocido'),
				{
					engine: probe.engine,
					model: probe.model,
					latency_ms: probe.latency_ms,
					label: probe.label,
					narrative: probe.narrative ?? null
				}
			);
		} catch (cause) {
			return failureFrom(cause, 'test-ai', 'No se pudo contactar la prueba del proveedor.');
		}
	},

	// Dedicated X-source action: the section owns its form (never nested in
	// the page form), so its PUT is PARTIAL — only these two keys travel and
	// every absent setting keeps its stored value.
	'save-x': async ({ request }) => {
		const form = await request.formData();
		const x_mode = text(form, 'x_mode');
		if (x_mode !== 'free' && x_mode !== 'paid') {
			return failure('save-x', 400, 'Elige el modo de X: gratuito o API de pago.');
		}

		try {
			// Empty key travels as '': the API masks the stored value on GET,
			// so '' is the documented keep-the-current sentinel, not a clear.
			await updateClientSettings({ x_mode, x_api_key: text(form, 'x_api_key') });
			return actionResult('save-x', true, X_SAVE_OK_MESSAGE);
		} catch (cause) {
			return failureFrom(cause, 'save-x', 'No se pudo guardar la configuración de X.');
		}
	},

	// Keyword CRUD for the embedded panel; shared handlers keep the semantics
	// identical to the former /keywords page.
	create: ({ request }) => handleKeywordCreate(request),
	toggle: ({ request }) => handleKeywordToggle(request),
	delete: ({ request }) => handleKeywordDelete(request)
};
