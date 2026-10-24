import { fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	activateFieldOperator,
	createFieldOperator,
	deactivateFieldOperator,
	inviteFieldOperator,
	listFieldOperators
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

export const load: PageServerLoad = async () => {
	try {
		const operators = await listFieldOperators();
		return { operators: operators.items };
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
