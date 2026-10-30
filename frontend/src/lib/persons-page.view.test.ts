// @vitest-environment jsdom
import { mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import type { PersonDetail, PersonSummary } from '$lib/api';

import PersonsPage from '../routes/persons/+page.svelte';
import PersonDetailPage from '../routes/persons/[id]/+page.svelte';

/**
 * Persons views (v3 «Panel de monitoreo»): directory panel with the
 * monogram/name/alias cell, plus the day-grouped mention timeline with
 * stamp/badges/quote. Copy stays «Personajes»; aliases render as
 * «También mencionado como»; no view toggle or sort selector.
 */

const mounted: Array<Record<string, unknown>> = [];

function person(overrides: Partial<PersonSummary> = {}): PersonSummary {
	return {
		id: 1,
		name: 'Alina Mejía',
		name_key: 'alina mejia',
		role: 'Directora general',
		org: 'Universidad Central',
		aliases: ['Mejía Ruiz'],
		first_seen_at: '2026-10-20T09:00:00Z',
		last_seen_at: '2026-10-27T21:30:00Z',
		mention_count: 7,
		...overrides
	};
}

function timelineItem(overrides: Partial<PersonDetail['timeline'][number]> = {}) {
	return {
		mention_id: 11,
		title: 'Nota sobre la universidad',
		url: 'https://example.com/nota',
		source: 'news_rss' as PersonDetail['timeline'][number]['source'],
		published_at: '2026-10-27T21:30:00Z',
		ingested_at: '2026-10-27T21:31:00Z',
		sentiment: 'positive' as PersonDetail['timeline'][number]['sentiment'],
		role: 'Directora general',
		org: null,
		context: 'Declaró ante la prensa sobre el proceso.',
		event_id: 42,
		event_title: 'Audiencia pública',
		political_label: null,
		...overrides
	};
}

function renderList(persons: PersonSummary[], q = '') {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(PersonsPage, {
		target,
		props: { params: {}, data: { persons, q }, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		root: target
	};
}

function renderDetail(personRow: PersonDetail) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(PersonDetailPage, {
		target,
		props: { params: { id: '1' }, data: { person: personRow }, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		root: target
	};
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

describe('persons list', () => {
	it('renders the v3 directory panel with monogram, alias line and counts', () => {
		const { text, root } = renderList([person(), person({ id: 2, name: 'Beto Lara', aliases: [] })]);

		expect(text()).toContain('Personajes');
		// Mockup «personajes.html»: page title + subtitles.people verbatim.
		expect(root.querySelector('h1.page-title')?.textContent).toBe('Personajes');
		expect(text()).toContain(
			'Quién aparece, en qué contexto y cómo evoluciona su presencia.'
		);
		// Mockup peopleView: panel header verbatim.
		expect(root.querySelector('.directory-header h2')?.textContent).toBe(
			'Directorio de personajes'
		);
		expect(text()).toContain('2 identidades detectadas');
		// Search: visible label + honest placeholder (backend q = name_key/alias_keys).
		expect(text()).toContain('Buscar por nombre');
		expect(root.querySelector<HTMLInputElement>('.directory-search input')?.placeholder).toBe(
			'Nombre o variante…'
		);
		// Toolbar: sort select behind the mockup's filter toggle.
		expect(root.querySelector('.directory-filter-toggle')?.getAttribute('aria-expanded')).toBe(
			'false'
		);
		expect(root.querySelector('.directory-filters.is-open')).toBeNull();
		expect(root.querySelectorAll('.directory-filters option').length).toBe(3);
		// Result heading + pagination per mockup directoryResults.
		expect(text()).toContain('2 identidades · 1–2 visibles');
		expect(text()).toContain('25 por página');
		expect(text()).toContain('Página 1 de 1');
		const prev = root.querySelector<HTMLButtonElement>(
			'.directory-pagination button:first-of-type'
		);
		expect(prev?.hasAttribute('disabled')).toBe(true);
		expect(root.querySelector('section.directory-panel')).toBeTruthy();
		expect(root.querySelectorAll('.directory-monogram').length).toBe(2);
		const name = root.querySelector<HTMLAnchorElement>('a.directory-name');
		expect(name?.getAttribute('href')).toBe('/persons/1');
		// Mockup columns verbatim; aliases are NOT a row element (they live in
		// the ficha dl «Variantes anotadas»).
		expect([...root.querySelectorAll('.directory-table th')].map((el) => el.textContent)).toEqual([
			'Identidad',
			'Tipo',
			'Menciones',
			'Fuentes',
			'Última aparición'
		]);
		expect(text()).not.toContain('También mencionado como');
		expect(root.querySelector('td[data-label="Tipo"]')?.textContent).toBe('Persona');
		const count = root.querySelector('td[data-label="Menciones"] strong');
		expect(count?.textContent).toBe('7');
		const seen = root.querySelector('td[data-label="Última aparición"] time');
		expect(seen?.getAttribute('datetime')).toBe('2026-10-27T21:30:00Z');
		expect(seen?.querySelector('.directory-time')).toBeTruthy();
		expect(root.querySelector('.directory-disclaimer')).toBeTruthy();
		expect(root.querySelector('details.directory-method')).toBeTruthy();
	});

	it('keeps the search form and shows the mockup empty state for a query', () => {
		const { text, root } = renderList([], 'rectoría');

		expect(root.querySelector('form[method="get"]')).toBeTruthy();
		const input = root.querySelector<HTMLInputElement>('input[name="q"]');
		expect(input?.value).toBe('rectoría');
		expect(root.querySelector('.directory-table')).toBeNull();
		// Mockup empty state (filters produce no identities).
		expect(text()).toContain('No hay identidades con estos filtros');
		expect(root.querySelector('a.button[href="/persons"]')?.textContent).toBe('Ver todos');
	});
});

describe('persons detail', () => {
	it('renders the v3 record: eyebrow, meta and day-grouped timeline', () => {
		const { text, root } = renderDetail({
			...person(),
			timeline: [
				timelineItem(),
				timelineItem({
					mention_id: 12,
					published_at: '2026-10-26T14:00:00Z',
					ingested_at: '2026-10-26T14:01:00Z',
					sentiment: null
				})
			]
		});

		// Mockup directoryDetail: eyebrow «PERSONA · id»; aliases live in the
		// meta dl as «Variantes anotadas», not in the header.
		expect(root.querySelector('.person-head .eyebrow')?.textContent?.trim()).toBe(
			'Persona · 1'
		);
		expect(text()).not.toContain('También mencionado como');
		const dts = [...root.querySelectorAll('.directory-detail-meta dt')].map((el) => el.textContent);
		expect(dts).toEqual(['Primera mención', 'Última mención', 'Variantes anotadas']);
		const variantes = [...root.querySelectorAll('.directory-detail-meta dd')].at(-1);
		expect(variantes?.textContent).toBe('Mejía Ruiz');

		// Two local days → two groups; stamp carries only the HH:MM.
		expect(root.querySelectorAll('.mention-day').length).toBe(2);
		expect(root.querySelectorAll('.mention-timeline-item').length).toBe(2);
		const stamp = root.querySelector('.mention-timeline-stamp time');
		expect(stamp?.textContent?.trim()).toMatch(/^\d{1,2}:\d{2}$/);
		expect(root.querySelector('.mention-badges .source-badge')).toBeTruthy();
		expect(root.querySelector('.tone-badge.tone-positive')).toBeTruthy();
		expect(
			root.querySelector('.mention-timeline-content blockquote.directory-quote')
		).toBeTruthy();
		expect(text()).toContain('Como: Directora general');
		const eventLink = root.querySelector<HTMLAnchorElement>('.event-ref a');
		expect(eventLink?.getAttribute('href')).toBe('/events/42');
		const title = root.querySelector<HTMLAnchorElement>('.mention-timeline-content h4 a');
		expect(title?.getAttribute('href')).toBe('https://example.com/nota');
	});

	it('groups same-day mentions into a single day and keeps the empty state', () => {
		const sameDay = renderDetail({
			...person(),
			timeline: [timelineItem(), timelineItem({ mention_id: 12 })]
		});
		expect(sameDay.text()).toContain('2 menciones');
		expect(sameDay.root.querySelectorAll('.mention-day').length).toBe(1);
		expect(sameDay.root.querySelectorAll('.mention-timeline-item').length).toBe(2);

		const empty = renderDetail({ ...person(), timeline: [] });
		expect(empty.text()).toContain('Sin menciones registradas.');
		expect(empty.root.querySelector('.mention-timeline')).toBeNull();
	});
});
