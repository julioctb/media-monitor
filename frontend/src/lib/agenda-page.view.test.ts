// @vitest-environment jsdom
import { mount, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { AgendaItem } from '$lib/api';

import AgendaPage from '../routes/agenda/+page.svelte';

/**
 * Agenda page view (feature agenda-page): the mockup contract — intro,
 * filters, results with view toggle, «Sin fecha completa» bucket and both
 * forms — renders from the loaded items; empty states included.
 */

const mounted: Array<Record<string, unknown>> = [];

function item(overrides: Partial<AgendaItem>): AgendaItem {
	return {
		id: 1,
		client_id: 1,
		title: 'Taller de cáncer de mama',
		kind: 'activity',
		event_date: '2026-10-27',
		date_label: null,
		time_label: '11:00',
		location: 'Aula Magna B · Derecho',
		source: 'Resumen del día',
		url: null,
		notes: 'Taller incluido previamente en la agenda del resumen.',
		created_at: '2026-10-23T10:00:00Z',
		...overrides
	};
}

function renderPage(
	items: AgendaItem[],
	form: { form: string; message: string } | null = null
) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(AgendaPage, {
		target,
		props: { params: {}, data: { items }, form }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return { text: () => (target.textContent ?? '').replace(/\s+/g, ' ') };
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

it('renders the mockup structure with dated and undated buckets', () => {
	const { text } = renderPage([
		item({ id: 1 }),
		item({
			id: 2,
			title: 'Inscripciones para «Bestias Eternas»',
			kind: 'deadline',
			event_date: null,
			date_label: '15 nov.',
			time_label: null
		})
	]);

	expect(text()).toContain('Agenda');
	expect(text()).toContain('Añadir actividad');
	expect(text()).toContain('Actividades y plazos identificados en la cobertura');
	expect(text()).toContain('Buscar en la agenda');
	expect(text()).toContain('Actividades detectadas');
	expect(text()).toContain('Calendario');
	expect(text()).toContain('Lista');
	expect(text()).toContain('Sin fecha completa');
	expect(text()).toContain('Solo aparecen aquí los registros que aún no indican día y mes.');
	// Card anatomy via the undated bucket (visible in every view) + calendar.
	expect(text()).toContain('Inscripciones para «Bestias Eternas»');
	expect(text()).toContain('Plazo de inscripción');
	expect(text()).toContain('Fuente: Resumen del día');
	expect(text()).toContain('Editar fecha');
	expect(text()).toContain('Mes actual');
});

it('shows the empty state without items', () => {
	const { text } = renderPage([]);
	expect(text()).toContain('No hay actividades para mostrar.');
	expect(text()).toContain('Nada pendiente de fecha.');
});

it('surfaces the action error message from the form result', () => {
	const { text } = renderPage([], { form: 'create', message: 'El título es obligatorio.' });
	expect(text()).toContain('El título es obligatorio.');
});
