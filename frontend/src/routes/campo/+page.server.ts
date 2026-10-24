import { fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	approveFieldReport,
	listFieldReports,
	rejectFieldReport,
	updateFieldReport
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const ID_RE = /^\d+$/;

export const load: PageServerLoad = async () => {
	try {
		const [pending, recent] = await Promise.all([
			listFieldReports('review'),
			listFieldReports()
		]);
		return {
			pending: pending.items,
			recent: recent.items.filter((report) => report.status !== 'review').slice(0, 30)
		};
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw fail(status, { message: `No se pudo cargar la cola: ${detail}` });
	}
};

export const actions: Actions = {
	approve: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		if (!ID_RE.test(String(form.get('id')))) {
			return fail(400, { message: 'Id inválido.' });
		}
		try {
			await approveFieldReport(id);
			return { ok: true, message: 'Reporte publicado en el feed.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo publicar el reporte.')
			});
		}
	},

	reject: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		if (!ID_RE.test(String(form.get('id')))) {
			return fail(400, { message: 'Id inválido.' });
		}
		const note = String(form.get('note') ?? '').trim() || null;
		try {
			await rejectFieldReport(id, note);
			return { ok: true, message: 'Reporte rechazado.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo rechazar el reporte.')
			});
		}
	},

	update: async ({ request }) => {
		const form = await request.formData();
		const id = Number(form.get('id'));
		if (!ID_RE.test(String(form.get('id')))) {
			return fail(400, { message: 'Id inválido.' });
		}
		const patch: Record<string, string> = {};
		for (const key of ['title', 'content', 'place'] as const) {
			const value = String(form.get(key) ?? '').trim();
			if (value) patch[key] = value;
		}
		if (!Object.keys(patch).length) {
			return fail(400, { message: 'Nada que guardar.' });
		}
		try {
			await updateFieldReport(id, patch);
			return { ok: true, message: 'Reporte actualizado.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo actualizar el reporte.')
			});
		}
	}
};
