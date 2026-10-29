// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, tick, unmount } from 'svelte';

import EventsPage from './+page.svelte';
import type { PageProps } from './$types';
import type { EventSummary } from '$lib/api';

function event(over: Partial<EventSummary> & Pick<EventSummary, 'id'>): EventSummary {
	return {
		title: 'Evento de prueba',
		mention_count: 1,
		source_count: 1,
		summary: null,
		first_seen_at: '2026-10-27T15:00:00+00:00',
		last_seen_at: '2026-10-27T18:00:00+00:00',
		...over
	};
}

function baseData() {
	return {
		// eco (2+ fuentes) / sin eco / sin eco, para poblar los dos grupos.
		events: [
			event({
				id: 31,
				title: 'Aumento tarifario en el transporte',
				summary: 'El ayuntamiento anunció el ajuste para diciembre.',
				mention_count: 3,
				source_count: 2
			}),
			event({
				id: 7,
				title: 'Renuncia en el consejo universitario',
				mention_count: 2,
				source_count: 1
			}),
			event({
				id: 12,
				title: 'Cierre de convocatoria de becas',
				mention_count: 1,
				source_count: 1
			})
		],
		prefs: { saved: [] as number[], follow: [] as number[], seen: {} as Record<string, string> },
		scope: 'eco' as const
	};
}

const mounted: unknown[] = [];

function renderPage(data: Record<string, unknown>) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(EventsPage, {
		target,
		props: {
			params: {} as PageProps['params'],
			data: data as PageProps['data'],
			form: null
		}
	});
	mounted.push(instance);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		query: (selector: string) => target.querySelector(selector),
		queryAll: (selector: string) => [...target.querySelectorAll(selector)],
		target
	};
}

function type(container: HTMLElement, value: string) {
	const input = container.querySelector('#events-search') as HTMLInputElement;
	input.value = value;
	input.dispatchEvent(new Event('input', { bubbles: true }));
}

afterEach(() => {
	while (mounted.length) {
		const instance = mounted.pop();
		if (instance) unmount(instance as never);
	}
	document.cookie = 'mm_prefs=; max-age=0; path=/';
});

describe('events view (mockup eventView)', () => {
	it('renders toolbar, provenance note and both coverage groups with sub-counts', () => {
		const page = renderPage(baseData());
		const text = page.text();

		expect(text).toContain('Los eventos reúnen menciones del mismo hecho');
		expect(text).toContain('no constituyen confirmación independiente');
		expect(page.query('.events-toolbar')).not.toBeNull();
		expect(page.query('#events-search')).not.toBeNull();
		expect(page.query('#events-count')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'3 de 3 eventos'
		);

		const groups = page.queryAll('section.events-group');
		expect(groups).toHaveLength(2);
		expect(groups[0].querySelector('h2')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'Con eco de medios'
		);
		expect(groups[0].querySelector('.sub-count')?.textContent?.trim()).toBe('1');
		expect(groups[1].querySelector('h2')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'Otros eventos'
		);
		expect(groups[1].querySelector('.sub-count')?.textContent?.trim()).toBe('2');

		// estructura mockup: las cards cuelgan directo del grid de sección
		expect(page.queryAll('.section-grid .event-card')).toHaveLength(3);
		// el routeo al detalle sobrevive: headline -> /events/:id
		const link = page.query('.event-card h3 a[href="/events/31"]');
		expect(link).not.toBeNull();

		// el segmented eco/todas v1 quedó fuera del DOM (el scope vive solo en el load)
		expect(page.query('.segmented')).toBeNull();
	});

	it('degrades to the mockup single «Eventos identificados» group without echo', () => {
		const data = baseData();
		const onlySingleSource = (data.events as EventSummary[]).map((e) => ({ ...e, source_count: 1 }));
		const page = renderPage({ ...data, events: onlySingleSource });

		const groups = page.queryAll('section.events-group');
		expect(groups).toHaveLength(1);
		expect(groups[0].querySelector('h2')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'Eventos identificados'
		);
		expect(groups[0].querySelectorAll('.event-card')).toHaveLength(3);
	});

	it('filters the loaded set client-side from the toolbar search', async () => {
		const page = renderPage(baseData());
		type(page.target, 'tarifa');
		await tick();

		expect(page.query('#events-count')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'1 de 3 eventos'
		);
		expect(page.queryAll('.section-grid .event-card')).toHaveLength(1);
		expect(page.text()).toContain('Aumento tarifario en el transporte');

		type(page.target, 'zzz-sin-coincidencia');
		await tick();
		expect(page.text()).toContain('No se encontraron eventos');
		expect(page.text()).toContain('Prueba con otro número o asunto.');
	});

	it('keeps an honest empty state when no events exist at all', () => {
		const page = renderPage({ events: [], scope: 'eco', prefs: { saved: [], follow: [], seen: {} } });

		expect(page.queryAll('section.events-group')).toHaveLength(0);
		expect(page.text()).toContain('Sin eventos registrados todavía.');
		expect(page.query('#events-count')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'0 de 0 eventos'
		);
	});
});

describe('events follow (mockup data-follow)', () => {
	it('seeds the pressed state from the server prefs and toggles the cookie', async () => {
		const data = baseData();
		data.prefs = { saved: [], follow: [31], seen: {} };
		const page = renderPage(data);
		await tick();

		const states = page.queryAll('.event-card .event-card-footer button').map((button) => ({
			label: button.textContent?.replace(/\s+/g, ' ').trim(),
			pressed: button.getAttribute('aria-pressed'),
			primary: button.classList.contains('primary')
		}));
		// el seguido (31) va en estado «Siguiendo»; el resto ofrece «Seguir evento»
		expect(states.filter((s) => s.label === 'Siguiendo')).toHaveLength(1);
		const following = states.find((s) => s.label === 'Siguiendo')!;
		expect(following.pressed).toBe('true');
		expect(following.primary).toBe(true);

		const followButtons = page.queryAll('.event-card .event-card-footer button');
		const pending = followButtons.find((b) => b.textContent?.includes('Seguir evento'))!;
		pending.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		await tick();
		expect(pending.textContent?.replace(/\s+/g, ' ')).toContain('Siguiendo');
		expect(document.cookie).toContain('mm_prefs=');

		const unfollow = followButtons.find((b) => b.getAttribute('aria-pressed') === 'true')!;
		unfollow.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		await tick();
		expect(unfollow.textContent?.replace(/\s+/g, ' ')).toContain('Seguir evento');
	});
});
