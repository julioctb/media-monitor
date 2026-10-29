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
		// El split de grupos es por seguimiento, no por cobertura: el mix de
		// source_count solo decora. El pool completo lo fija el load.
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
			event({ id: 12, title: 'Cierre de convocatoria de becas', mention_count: 1, source_count: 1 })
		],
		prefs: { saved: [] as number[], follow: [] as number[], seen: {} as Record<string, string> }
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

function press(button: Element) {
	button.dispatchEvent(new MouseEvent('click', { bubbles: true }));
}

function pressedButtons(page: ReturnType<typeof renderPage>) {
	return page
		.queryAll('.event-card .event-card-footer button')
		.filter((button) => button.getAttribute('aria-pressed') === 'true');
}

afterEach(() => {
	while (mounted.length) {
		const instance = mounted.pop();
		if (instance) unmount(instance as never);
	}
	document.cookie = 'mm_prefs=; max-age=0; path=/';
});

describe('events view (mockup eventView)', () => {
	it('renders toolbar, provenance note and both follow groups with sub-counts', () => {
		const data = baseData();
		data.prefs.follow = [31];
		const page = renderPage(data);
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
			'En seguimiento'
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

		// sin toggle v1: ni segmented ni eje de cobertura en el DOM
		expect(page.query('.segmented')).toBeNull();
	});

	it('degrades to the mockup single «Eventos identificados» group without follows', () => {
		const page = renderPage(baseData());

		const groups = page.queryAll('section.events-group');
		expect(groups).toHaveLength(1);
		expect(groups[0].querySelector('h2')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'Eventos identificados'
		);
		expect(groups[0].querySelectorAll('.event-card')).toHaveLength(3);
	});

	it('regroups a card under «En seguimiento» when follow toggles', async () => {
		const page = renderPage(baseData());
		await tick();

		const target = page
			.queryAll('.event-card')
			.find((card) => card.querySelector('a[href="/events/7"]'))!;
		const button = target.querySelector('.event-card-footer button')!;
		expect(button.textContent?.replace(/\s+/g, ' ')).toContain('Seguir evento');
		press(button);
		await tick();

		// la card 7 se movió de grupo: ahora vive en «En seguimiento»
		const groups = page.queryAll('section.events-group');
		expect(groups).toHaveLength(2);
		expect(groups[0].querySelector('h2')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'En seguimiento'
		);
		const followedLinks = [...groups[0].querySelectorAll('.event-card h3 a')].map((a) =>
			a.getAttribute('href')
		);
		expect(followedLinks).toContain('/events/7');
		expect(groups[1].querySelector('h2')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'Otros eventos'
		);
	});

	it('filters the loaded set client-side from the toolbar search', async () => {
		const page = renderPage(baseData());
		// mayúsculas a propósito: el plegado va con locale es, como el mockup
		type(page.target, 'TARIFA');
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
		const page = renderPage({ events: [], prefs: { saved: [], follow: [], seen: {} } });

		expect(page.queryAll('section.events-group')).toHaveLength(0);
		expect(page.text()).toContain('Sin eventos registrados todavía.');
		expect(page.query('#events-count')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'0 de 0 eventos'
		);
	});
});

describe('events follow (mockup data-follow)', () => {
	it('seeds the pressed state, groups followed cards and toggles the cookie', async () => {
		const data = baseData();
		data.prefs = { saved: [], follow: [31], seen: {} };
		const page = renderPage(data);
		await tick();

		// el seguido (31) renderiza pressionado y dentro de «En seguimiento»
		expect(pressedButtons(page)).toHaveLength(1);
		const seeded = pressedButtons(page)[0]!;
		expect(seeded.closest('section')?.querySelector('h2')?.textContent).toContain(
			'En seguimiento'
		);
		expect(seeded.textContent?.replace(/\s+/g, ' ')).toContain('Siguiendo');
		expect(seeded.classList.contains('primary')).toBe(true);

		// seguir 7: cookie escrita y card re-agrupada (el move recrea el nodo)
		const pending = page
			.queryAll('.event-card .event-card-footer button')
			.find((button) => button.textContent?.includes('Seguir evento'))!;
		const pendingHref = pending
			.closest('.event-card')
			?.querySelector('.headline a')
			?.getAttribute('href');
		press(pending);
		await tick();
		expect(document.cookie).toContain('mm_prefs=');

		const groups = page.queryAll('section.events-group');
		expect(groups).toHaveLength(2);
		const movedCard = [...groups[0].querySelectorAll('.event-card')].find(
			(card) => card.querySelector('.headline a')?.getAttribute('href') === pendingHref
		);
		expect(movedCard).toBeDefined();
		expect(movedCard!.querySelector('.event-card-footer button')?.textContent).toContain(
			'Siguiendo'
		);

		// volver a dejar de seguir 7 deja un solo pressionado (31)
		press(movedCard!.querySelector('.event-card-footer button')!);
		await tick();
		expect(pressedButtons(page)).toHaveLength(1);
	});
});
