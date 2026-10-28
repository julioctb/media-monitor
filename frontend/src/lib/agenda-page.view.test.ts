// @vitest-environment jsdom
import { mount, unmount, tick } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { AgendaItem } from '$lib/api';

import AgendaPage from '../routes/agenda/+page.svelte';

/**
 * Agenda page view (v3 «Panel de monitoreo» contract): intro with the
 * primary CTA, app filter row, calendar panel (toolbar + month grid +
 * day detail), schedule-row cards, «Sin fecha completa» bucket, both
 * forms, about details.
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

it('renders the v3 structure with month view and pending bucket', () => {
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
	expect(text()).toContain('Mes actual');
	// Calendar panel v3: toolbar count, interactive day cell with preview.
	expect(document.querySelector('.panel.calendar-panel')).toBeTruthy();
	expect(text()).toContain('con fecha en el mes');
	const dayButton = document.querySelector<HTMLButtonElement>('.calendar-day.has-events');
	expect(dayButton).toBeTruthy();
	expect(dayButton?.getAttribute('aria-label')).toContain('Taller de cáncer de mama');
	expect(dayButton?.querySelector('.calendar-preview')?.textContent).toContain('Taller');
	expect(document.querySelectorAll('.calendar-view-switch button').length).toBe(2);
	// Undated bucket: gated title with count, card rendered from the shared list.
	expect(text()).toContain('Sin fecha completa (1)');
	expect(text()).toContain('Inscripciones para «Bestias Eternas»');
	expect(text()).toContain('Plazo de inscripción');
	expect(text()).toContain('Fecha por confirmar');
	// Undated card anatomy: date box carries the raw label, kind pill.
	const undatedBox = document.querySelector('.activity .date-box');
	expect(undatedBox?.textContent).toContain('15 nov.');
	expect(document.querySelector('.activity .tone-badge')?.textContent).toBe(
		'Plazo de inscripción'
	);
	expect(text()).toContain('Lugar');
	expect(text()).toContain('Fuente');
	expect(text()).toContain('Editar fecha');
	expect(text()).toContain('Eliminar');
});

it('opens the day detail from a calendar day and clears it back to the month', async () => {
	renderPage([item({ id: 1 }), item({ id: 3, title: 'Segunda actividad del día' })]);
	await tick();
	const dayButton = document.querySelector<HTMLButtonElement>('.calendar-day.has-events');
	dayButton?.click();
	await tick();
	const body = () => (document.body.textContent ?? '').replace(/\s+/g, ' ');
	expect(body()).toContain('Actividades del 27 de octubre de 2026');
	expect(body()).toContain('Ver todo el mes');
	// Dated cards now render: schedule-row date box + kind pill.
	expect(document.querySelector('.activity .date-box strong')?.textContent).toBe('27');
	expect(document.querySelector('.activity .tone-badge')?.textContent).toBe('Actividad');
	const clear = [...document.querySelectorAll('button')].find(
		(b) => b.textContent?.trim() === 'Ver todo el mes'
	);
	clear?.click();
	await tick();
	expect(body()).not.toContain('Ver todo el mes');
	expect(body()).not.toContain('Actividades del 27 de octubre de 2026');
});

it('hides the pending bucket without undated items', () => {
	const { text } = renderPage([item({ id: 1 })]);
	expect(text()).not.toContain('Sin fecha completa');
	expect(text()).toContain('con fecha en el mes');
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
