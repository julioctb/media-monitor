import { error, fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import { ApiError, createAgendaItem, listAgendaItems, patchAgendaItem } from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function text(form: FormData, name: string): string {
	const value = form.get(name);
	return typeof value === 'string' ? value.trim() : '';
}

export const load: PageServerLoad = async () => {
	try {
		const items = await listAgendaItems();
		return { items };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudo cargar la agenda: ${detail}`);
	}
};

export const actions: Actions = {
	create: async ({ request }) => {
		const form = await request.formData();
		const title = text(form, 'title');
		if (!title) {
			return fail(400, { form: 'create', message: 'El título es obligatorio.' });
		}
		const kindRaw = text(form, 'kind');
		const kind = kindRaw === 'deadline' ? 'deadline' : 'activity';
		const event_date = text(form, 'event_date') || null;
		if (event_date && !DATE_RE.test(event_date)) {
			return fail(400, { form: 'create', message: 'Fecha inválida.' });
		}
		try {
			await createAgendaItem({
				title,
				kind,
				event_date,
				date_label: text(form, 'date_label') || null,
				time_label: text(form, 'time') || null,
				location: text(form, 'location') || null,
				source: text(form, 'source') || null,
				url: text(form, 'url') || null,
				notes: text(form, 'notes') || null
			});
		} catch (cause) {
			const status = cause instanceof ApiError && cause.status < 500 ? 400 : 502;
			return fail(status, {
				form: 'create',
				message: errorMessage(cause, 'No se pudo guardar la actividad.')
			});
		}
		return { form: 'create', ok: true };
	},

	editDate: async ({ request }) => {
		const form = await request.formData();
		const idRaw = text(form, 'id');
		const id = Number.parseInt(idRaw, 10);
		const event_date = text(form, 'event_date');
		if (!Number.isInteger(id) || !DATE_RE.test(event_date)) {
			return fail(400, { form: 'date', message: 'Se requiere una fecha válida.' });
		}
		try {
			await patchAgendaItem(id, { event_date });
		} catch (cause) {
			const status = cause instanceof ApiError && cause.status === 404 ? 404 : 502;
			return fail(status, {
				form: 'date',
				message: errorMessage(cause, 'No se pudo guardar la fecha.')
			});
		}
		return { form: 'date', ok: true };
	}
};
