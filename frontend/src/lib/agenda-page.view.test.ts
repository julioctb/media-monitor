// @vitest-environment jsdom
import { mount, unmount, tick } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { AgendaItem } from '$lib/api';

import AgendaPage from '../routes/agenda/+page.svelte';

/**
 * Agenda page view (mockup agenda-media-monitor contract): intro with the
 * primary CTA, toolbar with the view toggle, month grid + shared list,
 * «Sin fecha completa» bucket gated on data, both forms, about details.
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

it('renders the mockup structure with month view and pending bucket', () => {
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
	expect(text()).toContain('Buscar en la agenda');
	expect(text()).toContain('Calendario');
	expect(text()).toContain('Lista');
	expect(text()).toContain('Mes actual');
	// Undated bucket: gated title with count, card rendered from the shared list.
	expect(text()).toContain('Sin fecha completa (1)');
	expect(text()).toContain('Inscripciones para «Bestias Eternas»');
	expect(text()).toContain('Plazo de inscripción');
	expect(text()).toContain('Fecha por confirmar');
	// Card anatomy: details grid, edit affordance on every card.
	expect(text()).toContain('Lugar');
	expect(text()).toContain('Fuente');
	expect(text()).toContain('Editar fecha');
	expect(text()).toContain('Eliminar');
});

it('hides the pending bucket without undated items', () => {
	const { text } = renderPage([item({ id: 1 })]);
	expect(text()).not.toContain('Sin fecha completa');
	expect(text()).toContain('actividades con fecha completa en este mes');
});

it('shows the empty state on list view without matches', async () => {
	const page = renderPage([]);
	await tick();
	const listButton = [...document.querySelectorAll('button')].find(
		(b) => b.textContent?.trim() === 'Lista'
	);
	listButton?.click();
	await tick();
	const { text } = page;
	expect(text()).toContain('No hay actividades para mostrar');
	expect(text()).toContain('Prueba otra búsqueda o cambia el filtro.');
});

it('surfaces the action error message from the form result', () => {
	const { text } = renderPage([], { form: 'create', message: 'El título es obligatorio.' });
	expect(text()).toContain('El título es obligatorio.');
});
