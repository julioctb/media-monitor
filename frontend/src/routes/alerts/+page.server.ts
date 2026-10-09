import { error, fail } from '@sveltejs/kit';
import { ApiError, getAlertSettings, updateAlertSettings, type AlertDigest } from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const DIGESTS = new Set<AlertDigest>(['instant', 'daily', 'weekly']);
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

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

		if (!recipient_email || !EMAIL_RE.test(recipient_email)) {
			return fail(400, {
				ok: false,
				message: 'Ingresa un email de destino válido.',
				values: { digest, recipient_email, is_active }
			});
		}

		try {
			const saved = await updateAlertSettings({ digest, recipient_email, is_active });
			// Success: loads re-run, `data.settings` now matches the saved state.
			return {
				ok: true,
				message: 'Configuración guardada.',
				values: { digest: saved.digest, recipient_email: saved.recipient_email ?? '', is_active: saved.is_active }
			};
		} catch (cause) {
			const status = cause instanceof ApiError && cause.status >= 400 ? cause.status : 502;
			const message = cause instanceof Error ? cause.message : 'error desconocido';
			return fail(status, {
				ok: false,
				message,
				values: { digest, recipient_email, is_active }
			});
		}
	}
};
