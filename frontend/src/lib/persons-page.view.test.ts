// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { fromStore, get, writable } from 'svelte/store';

import type { PersonDetail, PersonSummary } from '$lib/api';
import type { MmPrefs } from '$lib/prefs';

import PersonsPage from '../routes/persons/+page.svelte';
import PersonDetailDialog from '$lib/components/PersonDetailDialog.svelte';
import DetailDialog from '$lib/components/DetailDialog.svelte';
import { prefs, seedPrefsFromServer } from '$lib/prefs';

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

function renderList(
	persons: PersonSummary[],
	q = '',
	followedPersons: number[] = []
) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const data = { persons, q, prefs: { ...emptyPrefs(), persons: followedPersons } };
	const instance = mount(PersonsPage, {
		target,
		props: { params: {}, data, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		root: target
	};
}

async function settle() {
	await new Promise((resolve) => setTimeout(resolve, 0));
	await tick();
}

async function renderDetail(personRow: PersonDetail, followedPersons: number[] = []) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	seedPrefsFromServer({ ...emptyPrefs(), persons: followedPersons });
	vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(personRow), {
		status: 200, headers: { 'content-type': 'application/json' }
	})));
	const instance = mount(PersonDetailDialog, {
		target, props: { person: personRow, onclose: () => {} }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	await settle();
	return { text: () => (target.textContent ?? '').replace(/\s+/g, ' '), root: target };
}

const originalShowModal = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'showModal');
const originalClose = Object.getOwnPropertyDescriptor(HTMLDialogElement.prototype, 'close');
beforeEach(() => {
	vi.stubGlobal('fetch', vi.fn());
	Object.defineProperty(HTMLDialogElement.prototype, 'showModal', {
		configurable: true, value() { this.setAttribute('open', ''); }
	});
	Object.defineProperty(HTMLDialogElement.prototype, 'close', {
		configurable: true, value() {
			if (!this.open) return;
			this.removeAttribute('open'); this.dispatchEvent(new Event('close'));
		}
	});
});

afterEach(async () => {
	while (mounted.length) await unmount(mounted.pop() as never);
	document.body.innerHTML = '';
	vi.unstubAllGlobals();
	if (originalShowModal) Object.defineProperty(HTMLDialogElement.prototype, 'showModal', originalShowModal);
	else delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).showModal;
	if (originalClose) Object.defineProperty(HTMLDialogElement.prototype, 'close', originalClose);
	else delete (HTMLDialogElement.prototype as Partial<HTMLDialogElement>).close;
});

describe('persons list', () => {
	it('requests the independent server timeline rather than the old capped ficha', async () => {
		const ficha = { ...person(), timeline: [timelineItem()] };
		const fetchMock = vi.fn(async (_input: RequestInfo | URL) => new Response(JSON.stringify(ficha), {
			status: 200, headers: { 'content-type': 'application/json' }
		}));
		vi.stubGlobal('fetch', fetchMock);
		const root = document.createElement('div');
		document.body.appendChild(root);
		mounted.push(mount(PersonsPage, { target: root, props: {
			params: {}, data: { persons: [person()], q: '', prefs: emptyPrefs() }, form: null
		}}) as unknown as Record<string, unknown>);
		root.querySelector<HTMLElement>('.directory-name')!.click();
		await new Promise((resolve) => setTimeout(resolve, 0));
		await tick();
		expect(fetchMock.mock.calls.map((args) => args[0])).toEqual([
			'/api/persons/1?limit=25&offset=0&order=recent'
		]);
		expect(root.querySelector('a[href^="/persons/"]')).toBeNull();
		vi.unstubAllGlobals();
	});
	it('matches the productive search and responsive follow-filter disclosure', async () => {
		const { root } = renderList([person()]);
		const search = root.querySelector<HTMLInputElement>('input[name="q"]')!;
		expect(search.closest('label')?.textContent).toContain('Buscar por nombre');
		expect(search.autocomplete).toBe('off');
		expect(root.querySelector('.directory-search button[type="submit"]')).toBeNull();
		const toggle = root.querySelector<HTMLButtonElement>('.directory-filter-toggle')!;
		expect(toggle?.getAttribute('aria-expanded')).toBe('false');
		toggle.click();
		await tick();
		expect(toggle.getAttribute('aria-expanded')).toBe('true');
		expect(root.querySelector('.directory-productive-filters')?.classList.contains('is-open')).toBe(true);
		expect(root.querySelector('select')).toBeNull();
	});

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
		// Keep the current clickable mention header, not the older sort select.
		expect(root.querySelector('select')).toBeNull();
		expect(root.querySelector('.directory-filter-toggle')).toBeTruthy();
		expect(root.querySelector('.directory-filters')).toBeTruthy();
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
		const name = root.querySelector<HTMLButtonElement>('button.directory-name');
		expect(name?.getAttribute('aria-haspopup')).toBe('dialog');
		expect(root.querySelector('a[href^="/persons/"]')).toBeNull();
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

	it('opens the complete identity modal with page-scoped event context', async () => {
		const ficha = { ...person(), timeline: [timelineItem()], timeline_total: 1 };
		vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(ficha))));
		const { root } = renderList([person()]);

		root.querySelector<HTMLAnchorElement>('button.directory-name')?.click();
		// Let the injected bridge promise settle, then flush Svelte.
		await new Promise((resolve) => setTimeout(resolve, 0));
		await tick();

		const dialog = root.querySelector('dialog.detail-dialog');
		expect(dialog).toBeTruthy();
		expect(root.textContent).toContain('Ficha de persona');
		expect(root.textContent).toContain('Eventos de esta página');
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
			'Prueba otro nombre o cambia el filtro de seguimiento.'
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
		const firstRow = () => root.querySelector('button.directory-name')?.textContent;
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
		expect(root.querySelector('button.directory-name')?.textContent).toBe('Beto Lara');
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
	it('sorts and follows across the loaded pool, not just the first 25 rows', async () => {
		const people = Array.from({ length: 80 }, (_, i) => person({ id: i + 1, name: `Persona ${i + 1}`, mention_count: 100 - i }));
		const { root, text } = renderList(people, '', [80]);
		expect(root.querySelectorAll('.directory-table tbody tr')).toHaveLength(25);
		expect(text()).toContain('80 identidades detectadas · 1 en seguimiento');
		root.querySelector<HTMLButtonElement>('.directory-mobile-sort')!.click();
		await tick();
		expect(root.querySelector('.directory-name')?.textContent).toBe('Persona 80');
		expect(root.querySelector('[aria-sort]')?.getAttribute('aria-sort')).toBe('ascending');
		root.querySelectorAll<HTMLButtonElement>('.directory-segmented button')[1].click();
		await tick();
		expect(root.querySelectorAll('.directory-table tbody tr')).toHaveLength(1);
		expect(root.querySelector('.directory-name')?.textContent).toBe('Persona 80');
		expect(text()).toContain('1 identidad · 1–1 visibles');
	});


});

describe('persons detail', () => {
	it('renders the v3 record: eyebrow, meta and day-grouped timeline', async () => {
		const { text, root } = await renderDetail({
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
		expect(root.querySelector('.directory-detail-heading .daily-dialog-eyebrow')?.textContent?.trim()).toBe(
			'Persona · 1'
		);
		expect(text()).toContain('También mencionado como: Mejía Ruiz');
		const dts = [...root.querySelectorAll('.directory-detail-meta dt')].map((el) => el.textContent);
		expect(dts).toEqual(['Menciones', 'Primera mención', 'Última mención']);

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
		const title = root.querySelector<HTMLAnchorElement>('.mention-timeline-content a.text-link');
		expect(title?.getAttribute('href')).toBe('https://example.com/nota');
	});

	it('groups same-day mentions into a single day and keeps the empty state', async () => {
		const sameDay = await renderDetail({
			...person(),
			timeline: [timelineItem(), timelineItem({ mention_id: 12 })]
		});
		expect(sameDay.text()).toContain('2 menciones en esta página');
		expect(sameDay.root.querySelectorAll('.mention-day').length).toBe(1);
		expect(sameDay.root.querySelectorAll('.mention-timeline-item').length).toBe(2);

		const empty = await renderDetail({ ...person(), timeline: [] });
		expect(empty.text()).toContain('Sin menciones registradas en esta página.');
		expect(empty.root.querySelector('.mention-timeline')).toBeNull();
	});

	it('renders the existing follow button in the shared detail heading', async () => {
		const detail = await renderDetail({ ...person(), timeline: [] }, [1]);
		const heading = detail.root.querySelector('.directory-detail-heading');
		expect(heading).toBeTruthy();
		const btn = heading?.querySelector<HTMLButtonElement>('button');
		expect(btn?.getAttribute('aria-pressed')).toBe('true');
		expect(btn?.textContent).toContain('En seguimiento');

		const unfollowed = await renderDetail({ ...person(), timeline: [] });
		const btn2 = unfollowed.root.querySelector<HTMLButtonElement>('.directory-detail-heading button');
		expect(btn2?.getAttribute('aria-pressed')).toBe('false');
		expect(btn2?.textContent).toContain('Seguir persona');
	});

	it('paginates the timeline on the server without changing the directory page', async () => {
		const people = Array.from({ length: 30 }, (_, i) => person({ id: i + 1, name: `Persona ${i + 1}`, mention_count: 100 - i }));
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			const url = new URL(String(input), 'http://localhost');
			const offset = Number(url.searchParams.get('offset'));
			return new Response(JSON.stringify({ ...people[0], timeline_total: 30, timeline_limit: 25,
				timeline_offset: offset, timeline_order: 'recent',
				timeline: Array.from({ length: offset === 0 ? 25 : 5 }, (_, i) => timelineItem({ mention_id: offset + i + 1 }))
			}));
		});
		vi.stubGlobal('fetch', fetchMock);
		const { root, text } = renderList(people);
		root.querySelector<HTMLButtonElement>('button.directory-name')!.click();
		await settle();
		expect(root.querySelectorAll('.mention-timeline-item')).toHaveLength(25);
		expect(text()).toContain('Cronología de menciones · 30');
		root.querySelector<HTMLButtonElement>('[data-timeline-next]')!.click();
		await settle();
		expect(root.querySelectorAll('.mention-timeline-item')).toHaveLength(5);
		expect(root.querySelector('dialog')?.textContent?.replace(/\s+/g, ' ')).toContain('Página 2 de 2');
		expect(root.querySelector('section.directory-panel .directory-pagination')?.textContent).toContain('Página 1 de 2');
		expect(fetchMock.mock.calls.map(([url]) => String(url))).toEqual([
			'/api/persons/1?limit=25&offset=0&order=recent',
			'/api/persons/1?limit=25&offset=25&order=recent'
		]);
	});
	it('keeps cookie-backed person following independent of event and saved preferences', async () => {
		const { root } = await renderDetail({ ...person(), timeline: [] });
		seedPrefsFromServer({ saved: [4], follow: [8], persons: [], seen: { '8': 'unchanged' } });
		await tick();
		root.querySelector<HTMLButtonElement>('.directory-detail-heading button')!.click();
		await tick();
		expect(get(prefs)).toEqual({ saved: [4], follow: [8], persons: [1], seen: { '8': 'unchanged' } });
		expect(root.querySelector('[aria-pressed]')?.getAttribute('aria-pressed')).toBe('true');
	});

	it.each(['javascript:alert(1)', '//example.com/nota', 'data:text/html,unsafe'])('keeps unsafe publication URL inert: %s', async (url) => {
		const { root, text } = await renderDetail({ ...person(), timeline: [timelineItem({ url, context: '<script>literal quotation</script>' })] });
		expect(root.querySelector('a[href="' + url + '"]')).toBeNull();
		expect(root.querySelector('script')).toBeNull();
		expect(text()).toContain('<script>literal quotation</script>');
	});

	it('ignores a pending response after close and reopen for another identity', async () => {
		const pending: Array<(response: Response) => void> = [];
		const fetchMock = vi.fn((_input: RequestInfo | URL) => new Promise<Response>((resolve) => pending.push(resolve)));
		vi.stubGlobal('fetch', fetchMock);
		const second = person({ id: 2, name: 'Beto Lara' });
		const { root } = renderList([person(), second]);
		root.querySelector<HTMLButtonElement>('.directory-name')!.click();
		await tick();
		root.querySelector<HTMLButtonElement>('dialog [aria-label="Cerrar detalle"]')!.click();
		await tick();
		root.querySelectorAll<HTMLButtonElement>('.directory-name')[1].click();
		await tick();
		pending[1](new Response(JSON.stringify({ ...second, timeline: [timelineItem({ context: 'Current identity' })] })));
		await settle();
		pending[0](new Response(JSON.stringify({ ...person(), timeline: [timelineItem({ context: 'Stale identity' })] })));
		await settle();
		expect(root.querySelector('dialog h2')?.textContent).toBe('Beto Lara');
		expect(root.querySelector('dialog')?.textContent).toContain('Current identity');
		expect(root.querySelector('dialog')?.textContent).not.toContain('Stale identity');
		expect(fetchMock).toHaveBeenCalledTimes(2);
	});

});

describe('modal states and closure', () => {
	it('opens only a modal, fetches same-origin detail, groups days and paginates with fallback metadata', async () => {
		const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
			expect(String(input)).toBe('/api/persons/1?limit=25&offset=0&order=recent');
			return new Response(
				JSON.stringify({
					...person(),
					timeline: [timelineItem(), timelineItem({ mention_id: 12 })]
				}),
				{ status: 200, headers: { 'content-type': 'application/json' } }
			);
		});
		vi.stubGlobal('fetch', fetchMock);
		const { root } = renderList([person(), person({ id: 2, name: 'Beto Lara', aliases: [] })]);
		root.querySelector<HTMLButtonElement>('button.directory-name')?.click();
		await new Promise((resolve) => setTimeout(resolve, 0));
		await tick();

		const dialog = root.querySelector('dialog.person-detail');
		expect(dialog?.hasAttribute('open')).toBe(true);
		expect(dialog?.querySelectorAll('.mention-day')).toHaveLength(1);
		expect(dialog?.querySelectorAll('.mention-timeline-item')).toHaveLength(2);
		expect(dialog?.textContent).toContain('También mencionado como: Mejía Ruiz');
		expect(dialog?.textContent).toContain('Primera mención');
		expect(dialog?.textContent).toContain('Página 1');
		expect(dialog?.textContent).not.toContain('Menciones totales del historial');
		expect(dialog?.querySelector<HTMLButtonElement>('[data-timeline-next]')?.disabled).toBe(true);
	});

	it('renders loading, error and empty timeline states from the same modal', async () => {
		let resolveRequest!: (response: Response) => void;
		vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => (resolveRequest = resolve))));
		const { root } = renderList([person(), person({ id: 2, name: 'Beto Lara', aliases: [] })]);
		root.querySelector<HTMLButtonElement>('button.directory-name')?.click();
		await tick();
		expect(root.querySelector('dialog.person-detail [role="status"]')?.textContent).toContain('Cargando ficha');
		resolveRequest(new Response('falló', { status: 503 }));
		await new Promise((resolve) => setTimeout(resolve, 0));
		await tick();
		expect(root.querySelector('[role="alert"]')?.textContent).toContain('No se pudo cargar');

		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				new Response(JSON.stringify({ ...person(), timeline: [], timeline_total: 0 }), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
		);
		root.querySelector<HTMLButtonElement>('dialog.person-detail [aria-label="Cerrar detalle"]')?.click();
		await tick();
		root.querySelectorAll<HTMLButtonElement>('button.directory-name')[1]?.click();
		await new Promise((resolve) => setTimeout(resolve, 0));
		await tick();
		expect(root.querySelector('dialog.person-detail')?.textContent).toContain('Sin menciones registradas');
	});

	it.each(['button', 'escape', 'backdrop'])('closes by %s and returns focus to its trigger', async (path) => {
		vi.stubGlobal(
			'fetch',
			vi.fn(async () =>
				new Response(JSON.stringify({ ...person(), timeline: [] }), {
					status: 200,
					headers: { 'content-type': 'application/json' }
				})
			)
		);
		const { root } = renderList([person(), person({ id: 2, name: 'Beto Lara', aliases: [] })]);
		const trigger = root.querySelector<HTMLButtonElement>('button.directory-name')!;
		trigger.focus();
		trigger.click();
		await tick();
		const dialog = root.querySelector<HTMLDialogElement>('dialog.person-detail')!;
		if (path === 'button') dialog.querySelector<HTMLButtonElement>('[aria-label="Cerrar detalle"]')?.click();
		else if (path === 'escape') dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
		else dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		await tick();
		expect(dialog.hasAttribute('open')).toBe(false);
		expect(document.activeElement).toBe(trigger);
	});
});

describe('shared dialog regression', () => {
	it('closes native chrome when the parent clears open and restores focus once', async () => {
		const target = document.createElement('div');
		const trigger = document.createElement('button');
		document.body.append(trigger, target);
		trigger.focus();
		const state = writable(true);
		const current = fromStore(state);
		const onclose = vi.fn();
		const instance = mount(DetailDialog, { target, props: {
			titleId: 'parent-close-title', title: 'Detalle', get open() { return current.current; }, onclose
		}});
		mounted.push(instance as unknown as Record<string, unknown>);
		await tick();
		const dialog = target.querySelector<HTMLDialogElement>('dialog')!;
		expect(dialog.open).toBe(true);
		state.set(false);
		await tick();
		expect(dialog.open).toBe(false);
		expect(onclose).toHaveBeenCalledOnce();
		expect(document.activeElement).toBe(trigger);
	});
	it('keeps backdrop clicks inert unless the optional behavior is enabled', async () => {
		const target = document.createElement('div');
		document.body.appendChild(target);
		const onclose = vi.fn();
		const instance = mount(DetailDialog, {
			target,
			props: { titleId: 'shared-title', title: 'Detalle', open: true, onclose }
		});
		mounted.push(instance as unknown as Record<string, unknown>);
		await tick();
		const dialog = target.querySelector<HTMLDialogElement>('dialog')!;
		dialog.dispatchEvent(new MouseEvent('click', { bubbles: true }));
		expect(dialog.hasAttribute('open')).toBe(true);
		expect(onclose).not.toHaveBeenCalled();
	});
});
