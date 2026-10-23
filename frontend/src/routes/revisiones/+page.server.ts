import { error, fail } from '@sveltejs/kit';
import { errorStatus, errorMessage } from '$lib/server/api-error';
import {
	listSummaryRevisionDays,
	listSummaryRevisions,
	restoreSummaryRevision
} from '$lib/api';
import type { Actions, PageServerLoad } from './$types';

const DAY_RE = /^\d{4}-\d{2}-\d{2}$/;

interface RestoreResult {
	ok: boolean;
	message: string;
}

export const load: PageServerLoad = async ({ url }) => {
	const dayParam = url.searchParams.get('day');
	const day = dayParam && DAY_RE.test(dayParam) ? dayParam : null;
	try {
		const days = await listSummaryRevisionDays();
		// Default view: the newest day with history, so the page never opens empty.
		// '' when there is no history: the page treats falsy as none, and the
		// serialized type stays a plain string.
		const selected = day ?? days[0]?.summary_date ?? '';
		const revisions = selected ? await listSummaryRevisions(selected) : [];
		return { days, selectedDay: selected, revisions };
	} catch (cause) {
		const status = errorStatus(cause, 503);
		const detail = errorMessage(cause, 'error desconocido');
		throw error(status, `No se pudo cargar el historial de narrativas: ${detail}`);
	}
};

export const actions: Actions = {
	restore: async ({ request }) => {
		const form = await request.formData();
		const day = String(form.get('day') ?? '').trim();
		const seqRaw = String(form.get('seq') ?? '').trim();
		const seq = /^\d+$/.test(seqRaw) ? Number(seqRaw) : 0;
		if (!DAY_RE.test(day) || seq < 1) {
			return fail(400, { ok: false, message: 'Petición de restauración inválida.' });
		}
		try {
			const row = await restoreSummaryRevision(day, seq);
			return {
				ok: true,
				message: `Versión ${seq} aplicada al ${row.summary_date}.`
			} satisfies RestoreResult;
		} catch (cause) {
			const status = errorStatus(cause, 502);
			return fail(status, {
				ok: false,
				message: `No se pudo restaurar: ${errorMessage(cause, 'error desconocido')}`
			} satisfies RestoreResult);
		}
	}
};
