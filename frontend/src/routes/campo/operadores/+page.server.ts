import { fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	activateFieldOperator,
	createFieldOperator,
	deactivateFieldOperator,
	inviteFieldOperator,
	listFieldOperators,
	listFieldReports
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		// Último reporte por operador: la API de operadores no expone la fecha;
		// se deriva aquí desde los reportes existentes (recepción `created_at`).
		const [operators, reports] = await Promise.all([listFieldOperators(), listFieldReports()]);
		const lastReportAt = new Map<number, string>();
		for (const report of reports.items) {
			if (report.operator_id == null || !report.created_at) continue;
			const current = lastReportAt.get(report.operator_id);
			if (!current || report.created_at > current) {
				lastReportAt.set(report.operator_id, report.created_at);
			}
		}
		// Orden alfabético (mockup field.js ordena el directorio por nombre).
		const items = operators.items
			.map((operator) => ({ ...operator, last_report_at: lastReportAt.get(operator.id) ?? null }))
			.sort((a, b) => a.display_name.localeCompare(b.display_name, 'es'));
		return { operators: items };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw fail(status, { message: `No se pudo cargar: ${detail}` });
	}
};

export const actions: Actions = {
	create: async ({ request }) => {
		const form = await request.formData();
		const display_name = String(form.get('display_name') ?? '').trim();
		const phone = String(form.get('phone') ?? '').trim();
		const tgRaw = String(form.get('telegram_user_id') ?? '').trim();
		if (!display_name || !phone) {
			return fail(400, { message: 'Nombre y teléfono son obligatorios.' });
		}
		const telegram_user_id = /^\d+$/.test(tgRaw) ? Number(tgRaw) : null;
		try {
			await createFieldOperator({ display_name, phone, telegram_user_id });
			return { ok: true, message: `Operador ${display_name} dado de alta.` };
		} catch (cause) {
			return fail(errorStatus(cause, 502), {
				message: errorMessage(cause, 'No se pudo dar de alta.')
			});
		}
	},

	invite: async ({ request }) => {
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

	activate: async ({ request }) => {
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

	deactivate: async ({ request }) => {
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
