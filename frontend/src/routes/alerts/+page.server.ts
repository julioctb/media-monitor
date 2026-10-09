import { error, fail } from '@sveltejs/kit';
import { ApiError, getAlertSettings, updateAlertSettings, type AlertDigest } from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const DIGESTS = new Set<AlertDigest>(['instant', 'daily', 'weekly']);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Shape echoed back to the form on every outcome (refill on errors). */
interface AlertFormValues {
	digest: AlertDigest;
	recipient_email: string;
	is_active: boolean;
	sentiment_shift_enabled: boolean;
	sentiment_shift_threshold: number;
}

export const load: PageServerLoad = async () => {
	try {
		return { settings: await getAlertSettings() };
	} catch (cause) {
		const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 503;
		const detail = cause instanceof Error ? cause.message : 'error desconocido';
		throw error(status, `No se pudo cargar la configuración de alertas: ${detail}`);
	}
};

export const actions: Actions = {
	save: async ({ request }) => {
		const form = await request.formData();
		const digestRaw = String(form.get('digest') ?? 'instant');
		const digest = (DIGESTS.has(digestRaw as AlertDigest) ? digestRaw : 'instant') as AlertDigest;
		const recipient_email = String(form.get('recipient_email') ?? '').trim();
		const is_active = form.get('is_active') === '1';

		// T4 sentiment-shift rule: absent checkbox = disabled; the threshold
		// is optional and keeps the stored value when blank.
		const sentiment_shift_enabled = form.get('sentiment_shift_enabled') === '1';
		const thresholdRaw = String(form.get('sentiment_shift_threshold') ?? '').trim();
		let sentiment_shift_threshold: number | undefined;
		if (thresholdRaw) {
			const parsed = Number(thresholdRaw);
			if (!Number.isFinite(parsed) || parsed <= 0 || parsed > 100) {
				return fail(400, {
					ok: false,
					message: 'El umbral de cambio de sentimiento debe estar entre 0 y 100.',
					values: {
						digest,
						recipient_email,
						is_active,
						sentiment_shift_enabled,
						sentiment_shift_threshold: parsed || 0
					} satisfies AlertFormValues
				});
			}
			sentiment_shift_threshold = parsed;
		}

		if (!recipient_email || !EMAIL_RE.test(recipient_email)) {
			return fail(400, {
				ok: false,
				message: 'Ingresa un email de destino válido.',
				values: {
					digest,
					recipient_email,
					is_active,
					sentiment_shift_enabled,
					sentiment_shift_threshold: sentiment_shift_threshold ?? 0
				} satisfies AlertFormValues
			});
		}

		try {
			const saved = await updateAlertSettings({
				digest,
				recipient_email,
				is_active,
				sentiment_shift_enabled,
				...(sentiment_shift_threshold !== undefined ? { sentiment_shift_threshold } : {})
			});
			// Success: loads re-run, `data.settings` now matches the saved state.
			return {
				ok: true,
				message: 'Configuración guardada.',
				values: {
					digest: saved.digest,
					recipient_email: saved.recipient_email ?? '',
					is_active: saved.is_active,
					sentiment_shift_enabled: saved.sentiment_shift_enabled,
					sentiment_shift_threshold: saved.sentiment_shift_threshold
				} satisfies AlertFormValues
			};
		} catch (cause) {
			const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 502;
			const message = cause instanceof Error ? cause.message : 'error desconocido';
			return fail(status, {
				ok: false,
				message,
				values: {
					digest,
					recipient_email,
					is_active,
					sentiment_shift_enabled,
					sentiment_shift_threshold: sentiment_shift_threshold ?? 0
				} satisfies AlertFormValues
			});
		}
	}
};
