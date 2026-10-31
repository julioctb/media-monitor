// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import type { PersonDetail, PersonSummary } from '$lib/api';
import type { MmPrefs } from '$lib/prefs';

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

const emptyPrefs = (): MmPrefs => ({ saved: [], follow: [], persons: [], seen: {} });

const neverFicha = async (): Promise<never> => {
	throw new Error('unexpected ficha load in this test');
};

function renderList(
	persons: PersonSummary[],
	q = '',
	followedPersons: number[] = [],
	loadFicha: (id: number) => Promise<PersonDetail> = neverFicha
) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const data = { persons, q, prefs: { ...emptyPrefs(), persons: followedPersons } };
	const instance = mount(PersonsPage, {
		target,
		props: { params: {}, data, form: null, loadFicha }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		root: target
	};
}

function renderDetail(personRow: PersonDetail, followedPersons: number[] = []) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const data = { person: personRow, prefs: { ...emptyPrefs(), persons: followedPersons } };
	const instance = mount(PersonDetailPage, {
		target,
		props: { params: { id: '1' }, data, form: null }
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
		expect(root.querySelector('.page-header h1')?.textContent).toBe('Personajes');
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
		// Sorting happens by clicking the columns: the «Ordenar por» select and
		// the mockup's filter toggle are gone (Julio: headers are the control).
		expect(root.querySelector('select')).toBeNull();
		expect(root.querySelector('.directory-filter-toggle')).toBeNull();
		expect(root.querySelector('.directory-filters')).toBeNull();
		const sortButtons = [...root.querySelectorAll('.directory-table th button')];
		expect(sortButtons.map((b) => b.textContent)).toEqual(['Menciones']);
		expect([
			...root.querySelectorAll('.directory-table th')
		].map((th) => th.getAttribute('aria-sort'))).toEqual([
			null,
			null,
			'descending',
			null,
			null
		]);
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

	it('opens the mockup «Ficha de identidad» dialog when a row is clicked', async () => {
		const ficha = { ...person(), timeline: [timelineItem()] };
		const { root } = renderList([person()], '', [], async () => ficha);

		root.querySelector<HTMLAnchorElement>('a.directory-name')?.click();
		// Let the injected bridge promise settle, then flush Svelte.
		await new Promise((resolve) => setTimeout(resolve, 0));
		await tick();

		const dialog = root.querySelector('dialog.detail-dialog');
		expect(dialog).toBeTruthy();
		expect(root.textContent).toContain('Ficha de identidad');
		expect(root.textContent).toContain('Eventos relacionados');
		expect(root.textContent).toContain('#42 · Audiencia pública');
		expect(root.textContent).toContain('Cronología de menciones · 1');
		const followBtn = root.querySelector<HTMLButtonElement>('dialog button[aria-pressed]');
		expect(followBtn?.textContent).toContain('Seguir persona');
	});

	it('keeps the search form and shows the mockup empty state for a query', () => {
		const { text, root } = renderList([], 'rectoría');

		expect(root.querySelector('form[method="get"]')).toBeTruthy();
		const input = root.querySelector<HTMLInputElement>('input[name="q"]');
		expect(input?.value).toBe('rectoría');
		expect(root.querySelector('.directory-table')).toBeNull();
		// Mockup empty state inside the results shell (heading + pagination stay).
		expect(text()).toContain('No hay identidades con estos filtros');
		expect(text()).toContain(
			'Prueba otro nombre o amplía los filtros. El ejemplo actual solo contiene organizaciones.'
		);
		expect(text()).toContain('0 identidades · 0–0 visibles');
		expect(text()).toContain('Página 1 de 1');
		// No «Limpiar filtros» action inside the empty state (Julio, L28).
		expect(root.querySelector('.empty .button')).toBeNull();
	});

	it('renders the mockup Todos/En seguimiento segmented control', () => {
		const { root } = renderList([person(), person({ id: 2, name: 'Beto Lara', aliases: [] })]);

		const group = root.querySelector('.directory-segmented');
		expect(group?.getAttribute('role')).toBe('group');
		expect(group?.getAttribute('aria-label')).toBe('Filtrar por seguimiento');
		const buttons = [...group!.querySelectorAll('button')];
		expect(buttons.map((b) => b.textContent)).toEqual(['Todos', 'En seguimiento']);
		expect(buttons[0]?.getAttribute('aria-pressed')).toBe('true');
		expect(buttons[0]?.classList.contains('active')).toBe(true);
		expect(buttons[1]?.getAttribute('aria-pressed')).toBe('false');
	});

	it('renders the Fuentes channel badges deduped in fixed mockup order', () => {
		const { root } = renderList([
			person({ sources: ['gdelt', 'news_rss', 'x_twitter', 'field_report'] })
		]);
		const badges = [...root.querySelectorAll('td[data-label="Fuentes"] .source-badge')];
		expect(badges.map((b) => [b.className, b.textContent?.trim()])).toEqual([
			['source-badge news', 'Noticias'],
			['source-badge social', 'Redes sociales'],
			['source-badge field', 'Campo']
		]);

		const plain = renderList([person({ id: 3, name: 'Sin Fuentes', sources: [] })]);
		expect(
			plain.root.querySelector('td[data-label="Fuentes"]')?.textContent?.trim()
		).toBe('—');
	});

	it('toggles direction on the Menciones header with honest aria-sort', async () => {
		const beto = person({
			id: 2,
			name: 'Beto Lara',
			aliases: [],
			mention_count: 900,
			last_seen_at: '2026-10-14T10:00:00Z'
		});
		const { root } = renderList([person(), beto]);
		const firstRow = () => root.querySelector('a.directory-name')?.textContent;
		const menciones = () =>
			root.querySelectorAll<HTMLTableCellElement>('.directory-table th')[2];
		const clickHeader = async () => {
			menciones().querySelector('button')!.click();
			await tick();
		};

		expect(firstRow()).toBe('Beto Lara'); // default: most mentioned first
		await clickHeader();
		expect(menciones().getAttribute('aria-sort')).toBe('ascending');
		expect(firstRow()).toBe('Alina Mejía');
		await clickHeader();
		expect(menciones().getAttribute('aria-sort')).toBe('descending');
		expect(firstRow()).toBe('Beto Lara');
	});

	it('counts followed persons in the header and filters with the segmented', async () => {
		const { text, root } = renderList(
			[person(), person({ id: 2, name: 'Beto Lara', aliases: [] })],
			'',
			[2]
		);
		expect(text()).toContain('2 identidades detectadas · 1 en seguimiento');

		const followedBtn = root.querySelectorAll<HTMLButtonElement>('.directory-segmented button')[1];
		followedBtn.click();
		await tick();
		expect(followedBtn.getAttribute('aria-pressed')).toBe('true');
		expect(root.querySelectorAll('.directory-table tbody tr')).toHaveLength(1);
		expect(root.querySelector('a.directory-name')?.textContent).toBe('Beto Lara');
		expect(text()).toContain('1 identidad · 1–1 visibles');

		root.querySelectorAll<HTMLButtonElement>('.directory-segmented button')[0].click();
		await tick();
		expect(root.querySelectorAll('.directory-table tbody tr')).toHaveLength(2);
	});

	it('shows the filter empty state when nothing is followed; Todos restores the list', async () => {
		const { text, root } = renderList([person()]);
		root.querySelectorAll<HTMLButtonElement>('.directory-segmented button')[1].click();
		await tick();
		expect(root.querySelector('.directory-table')).toBeNull();
		expect(text()).toContain('No hay identidades con estos filtros');
		// Mockup: results shell stays — 0–0 heading and disabled pagination.
		expect(text()).toContain('0 identidades · 0–0 visibles');
		expect(text()).toContain('Página 1 de 1');
		expect(root.querySelectorAll('.directory-pagination button[disabled]')).toHaveLength(2);
		expect(root.querySelector('.empty .button')).toBeNull();
		root.querySelectorAll<HTMLButtonElement>('.directory-segmented button')[0].click();
		await tick();
		expect(root.querySelectorAll('.directory-table tbody tr')).toHaveLength(1);
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

	it('renders the follow button in the detail heading (mockup directoryDetail)', () => {
		const detail = renderDetail({ ...person(), timeline: [] }, [1]);
		const heading = detail.root.querySelector('.directory-detail-heading');
		expect(heading).toBeTruthy();
		const btn = heading?.querySelector<HTMLButtonElement>('button');
		expect(btn?.getAttribute('aria-pressed')).toBe('true');
		expect(btn?.textContent).toContain('En seguimiento');

		const unfollowed = renderDetail({ ...person(), timeline: [] });
		const btn2 = unfollowed.root.querySelector<HTMLButtonElement>('.directory-detail-heading button');
		expect(btn2?.getAttribute('aria-pressed')).toBe('false');
		expect(btn2?.textContent).toContain('Seguir persona');
	});

	it('paginates the timeline at 25 mentions per page (mockup directoryDetail)', async () => {
		const timeline = Array.from({ length: 30 }, (_, i) =>
			timelineItem({ mention_id: i + 1 })
		);
		const { text, root } = renderDetail({ ...person(), timeline });

		expect(text()).toContain('Cronología de menciones · 30');
		expect(text()).toContain('Página 1 de 2');
		expect(text()).toContain('25 menciones en esta página');
		expect(root.querySelectorAll('.mention-timeline-item')).toHaveLength(25);

		root
			.querySelectorAll<HTMLButtonElement>('.directory-pagination button')[1]
			.click();
		await tick();
		expect(text()).toContain('Página 2 de 2');
		expect(text()).toContain('5 menciones en esta página');
		expect(root.querySelectorAll('.mention-timeline-item')).toHaveLength(5);
	});
});
