import { fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	activateFieldOperator,
	approveFieldReport,
	createFieldOperator,
	deactivateFieldOperator,
	inviteFieldOperator,
	listFieldOperators,
	listFieldReports,
	patchFieldOperator,
	rejectFieldReport,
	updateFieldReport
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const ID_RE = /^\d+$/;

function numericId(form: FormData): number | null {
	const raw = String(form.get('id') ?? '');
	return ID_RE.test(raw) ? Number(raw) : null;
}

export const load: PageServerLoad = async () => {
	try {
		const [pending, all, operators] = await Promise.all([
			listFieldReports('review'),
			listFieldReports(),
			listFieldOperators()
		]);
		// Último reporte por operador: la API de operadores no expone la fecha;
		// se deriva aquí desde los reportes existentes (recepción `created_at`).
		const lastReportAt = new Map<number, string>();
		for (const report of all.items) {
			if (report.operator_id == null || !report.created_at) continue;
			const current = lastReportAt.get(report.operator_id);
			if (!current || report.created_at > current) {
				lastReportAt.set(report.operator_id, report.created_at);
			}
		}
		// Orden alfabético (mockup field.js ordena el directorio por nombre).
		const operatorRows = operators.items
			.map((operator) => ({
				...operator,
				last_report_at: lastReportAt.get(operator.id) ?? null
			}))
			.sort((a, b) => a.display_name.localeCompare(b.display_name, 'es'));
		// `draft` (conversación de bot en curso) no entra a la bandeja.
		return {
			pending: pending.items,
			recent: all.items.filter(
				(report) => report.status === 'published' || report.status === 'rejected'
			),
			operators: operatorRows
		};
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw fail(status, { message: `No se pudo cargar Campo: ${detail}` });
	}
};

export const actions: Actions = {
	/** Publicar = guardar lo editado (titular/resumen) y aprobar, en un solo paso (mockup). */
	approve: async ({ request }) => {
		const form = await request.formData();
		const id = numericId(form);
		if (id === null) return fail(400, { message: 'Id inválido.' });
		const title = String(form.get('title') ?? '').trim();
		const content = String(form.get('content') ?? '').trim();
		if (!content) return fail(400, { message: 'Completa el resumen antes de publicar.' });
		try {
			await updateFieldReport(id, { title, content });
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
		const id = numericId(form);
		if (id === null) return fail(400, { message: 'Id inválido.' });
		const note = String(form.get('note') ?? '').trim();
		if (!note) return fail(400, { message: 'Indica el motivo de descarte.' });
		try {
			await rejectFieldReport(id, note);
			return { ok: true, message: 'Reporte descartado.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo descartar el reporte.')
			});
		}
	},

	createOperator: async ({ request }) => {
		const form = await request.formData();
		const display_name = String(form.get('display_name') ?? '').trim();
		const phone = String(form.get('phone') ?? '').trim();
		if (!display_name || !phone) {
			return fail(400, { message: 'Nombre y teléfono son obligatorios.' });
		}
		try {
			await createFieldOperator({ display_name, phone });
			return { ok: true, message: `Operador ${display_name} dado de alta.` };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo dar de alta.')
			});
		}
	},

	updateOperator: async ({ request }) => {
		const form = await request.formData();
		const id = numericId(form);
		if (id === null) return fail(400, { message: 'Id inválido.' });
		const display_name = String(form.get('display_name') ?? '').trim();
		const phone = String(form.get('phone') ?? '').trim();
		if (!display_name || !phone) {
			return fail(400, { message: 'Nombre y teléfono son obligatorios.' });
		}
		try {
			await patchFieldOperator(id, { display_name, phone });
			return { ok: true, message: 'Operador actualizado.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo guardar.')
			});
		}
	},

	inviteOperator: async ({ request }) => {
		const id = Number((await request.formData()).get('id'));
		if (!Number.isInteger(id)) return fail(400, { message: 'Id inválido.' });
		try {
			const invite = await inviteFieldOperator(id);
			return {
				ok: true,
				message: invite.link
					? `Link de invitación: ${invite.link}`
					: `Token generado: ${invite.token} (sin username de bot configurado)`,
				inviteLink: invite.link
			};
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo generar la invitación.')
			});
		}
	},

	activateOperator: async ({ request }) => {
		const id = Number((await request.formData()).get('id'));
		if (!Number.isInteger(id)) return fail(400, { message: 'Id inválido.' });
		try {
			await activateFieldOperator(id);
			return { ok: true, message: 'Operador activado.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo activar.')
			});
		}
	},

	deactivateOperator: async ({ request }) => {
		const id = Number((await request.formData()).get('id'));
		if (!Number.isInteger(id)) return fail(400, { message: 'Id inválido.' });
		try {
			await deactivateFieldOperator(id);
			return { ok: true, message: 'Operador desactivado.' };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo desactivar.')
			});
		}
	}
};
