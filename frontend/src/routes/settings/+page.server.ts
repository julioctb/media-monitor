import { error, fail } from '@sveltejs/kit';
import {
	ApiError,
	getClientSettings,
	listAvailableScrapers,
	testAi,
	testFacebookPage,
	updateClientSettings
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

/** Uniform action result: every branch carries the same keys for the view. */
interface SettingsActionResult {
	action: 'save' | 'test-facebook' | 'test-ai';
	ok: boolean;
	/** Banner text on save; probe outcome/error on the test actions. */
	message: string;
	/** Row index for test-facebook; -1 otherwise. */
	index: number;
	page_name: string | null;
	page_link: string | null;
	engine: string | null;
	model: string | null;
	latency_ms: number | null;
	label: string | null;
}

type ActionResultExtras = Partial<
	Pick<
		SettingsActionResult,
		'index' | 'page_name' | 'page_link' | 'engine' | 'model' | 'latency_ms' | 'label'
	>
>;

/** Probe-shaped defaults so callers only pass the fields they know. */
function actionResult(
	action: SettingsActionResult['action'],
	ok: boolean,
	message: string,
	extras: ActionResultExtras = {}
): SettingsActionResult {
	return {
		index: -1,
		page_name: null,
		page_link: null,
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
	const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 502;
	const message = cause instanceof Error && cause.message ? cause.message : fallback;
	return failure(action, status, message);
}

const SAVE_OK_MESSAGE = 'Configuración guardada.';

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

/** Zip the repeated row inputs by DOM order; drop fully empty rows. */
function readFacebookPages(
	form: FormData
): { page_id: string; token: string; label: string; kind: 'page' | 'group' }[] {
	const pageIds = form.getAll('fb_page_id').map((value) => String(value));
	const tokens = form.getAll('fb_token').map((value) => String(value));
	const labels = form.getAll('fb_label').map((value) => String(value));
	const kinds = form.getAll('fb_kind').map((value) => String(value));
	const pages: { page_id: string; token: string; label: string; kind: 'page' | 'group' }[] = [];
	for (let index = 0; index < pageIds.length; index += 1) {
		const page_id = (pageIds[index] ?? '').trim();
		const token = (tokens[index] ?? '').trim();
		const label = (labels[index] ?? '').trim();
		// Absent select (legacy row or older client) behaves as page, the
		// same default the backend credential applies.
		const kind: 'page' | 'group' = kinds[index] === 'group' ? 'group' : 'page';
		if (page_id === '' && token === '') continue;
		pages.push({ page_id, token, label, kind });
	}
	return pages;
}

export const load: PageServerLoad = async () => {
	try {
		// Best-effort: an unavailable registry must not block the page; the
		// card renders an empty state instead. Keywords feed the embedded
		// panel; a failure there degrades to an empty table.
		const scrapersAvailable = await listAvailableScrapers().catch(() => []);
		return { settings: await getClientSettings(), scrapersAvailable };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
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

		try {
			// Full-object PUT: the API keeps server-side fields (id, client_id,
			// updated_at) and validates the rest, mirroring the stored row.
			await updateClientSettings({
				client_name: text(form, 'client_name'),
				timezone: text(form, 'timezone'),
				retention_days,
				digest_hours,
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

	'test-facebook': async ({ request }) => {
		const form = await request.formData();
		// The probing button carries its row index; rows and inputs share one
		// DOM order, so the same index addresses every getAll() list.
		const index = Number.parseInt(text(form, 'probe_row') || '-1', 10);
		const row = index >= 0 ? readFacebookPages(form)[index] : undefined;

		if (!row || row.page_id === '' || row.token === '') {
			return actionResult(
				'test-facebook',
				false,
				'La fila necesita un page_id y un token para probarse.',
				{ index }
			);
		}

		try {
			const probe = await testFacebookPage({ page_id: row.page_id, token: row.token });
			return actionResult(
				'test-facebook',
				probe.ok,
				probe.ok ? 'Token verificado.' : String(probe.error ?? 'Error desconocido'),
				{ index, page_name: probe.name, page_link: probe.link }
			);
		} catch (cause) {
			return failureFrom(cause, 'test-facebook', 'No se pudo contactar la prueba de Facebook.');
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
					label: probe.label
				}
			);
		} catch (cause) {
			return failureFrom(cause, 'test-ai', 'No se pudo contactar la prueba del proveedor.');
		}
	}
};
