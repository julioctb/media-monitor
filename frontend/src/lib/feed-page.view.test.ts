// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';

import type { Mention } from '$lib/api';
import { toast } from '$lib/toast.svelte';
import Feed from '../routes/feed/+page.svelte';
import type { PageProps } from '../routes/feed/$types';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/feed?sentiment=negative&limit=1') } }));
vi.mock('$app/navigation', () => ({ invalidateAll: vi.fn() }));

const mounted: ReturnType<typeof mount>[] = [];
function dataFixture(): PageProps['data'] {
	return {
		mentions: { items: [{ id: 1, source: 'news_rss', title: 'Publicación sintética conservada', url: 'https://alpha.example/1', keyword_id: null, external_id: null, content: 'Contenido capturado.', summary: null, author: null, lang: 'es', published_at: '2026-10-14T12:00:00Z', ingested_at: '2026-10-14T12:00:00Z', sentiment: 'negative', sentiment_score: 0.2, reach: null, classifications: [], persons: [{ id: 3, name: 'Ana López' }], event_id: 1 }], total: 96 },
		keywords: [], digest: null,
		eventsById: {
			1: {
				id: 1,
				title: 'Evento sintético',
				mention_count: 2,
				source_count: 2,
				summary: 'Resumen del evento de prueba.',
				first_seen_at: '2026-10-13T12:00:00Z',
				last_seen_at: '2026-10-14T12:00:00Z',
				mentions: [
					{
						id: 1,
						source: 'news_rss',
						url: 'https://alpha.example/1',
						title: 'Publicación sintética conservada',
						sentiment: 'negative',
						published_at: '2026-10-14T12:00:00Z'
					}
				]
			}
		},
focusEvents: [],
		prefs: { saved: [], follow: [], seen: {} },
		sourceCounts: { news_rss: 200, x_twitter: 30 }, mediumCounts: { 'global.example': 200 }, newsMediumCount: 40,
		channelGroups: { news: ['news_rss'], social: ['x_twitter'], field: [] },
		feedStats: { total: 96, by_source: { news_rss: 96 }, by_sentiment: { negative: 96, positive: 0, neutral: 0, none: 0 }, news_medium_count: 17, result_group_count: 63 },
		feedStatsError: null,
		filters: { source: '', medium: '', channel: '', sentiment: 'negative', keyword_id: '', political: '', since: '', until: '', dateError: '', q: '', limit: 1, offset: 0 }
	};
}
async function render(data = dataFixture()) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	mounted.push(mount(Feed, { target, props: { params: {}, data, form: null } }));
	await tick();
	return target;
}
afterEach(async () => {
	for (const instance of mounted.splice(0)) await unmount(instance);
	document.body.replaceChildren();
	document.cookie = 'mm_prefs=; max-age=0; path=/';
});

it('exposes unavailable metrics without replacing measured values or loaded results', async () => {
	const data = dataFixture();
	data.feedStats = null;
	data.feedStatsError = 'Indicadores no disponibles: fallo sintético';
	const target = await render(data);
	expect([...target.querySelectorAll('.stat-value')].map((node) => node.textContent)).toEqual([
		'—',
		'—',
		'—',
		'—'
	]);
	for (const node of target.querySelectorAll('.stat-value')) {
		expect(node.getAttribute('title')).toBe('No disponible');
	}
	expect(target.querySelector('[role="status"]')?.textContent).toContain(data.feedStatsError);
	expect(target.querySelectorAll('.feed-group')).toHaveLength(1);
	expect(target.querySelector('.feed-match-count')?.textContent).toContain('96 publicaciones encontradas');
	expect(target.querySelector('a.page-button')?.textContent).toContain('Siguiente');
});

it('labels global navigation separately from filtered-result indicators', async () => {
	const target = await render();
	// v3 anatomy: the global-count note lives under Origen only
	expect(target.querySelector('[aria-labelledby="origen-title"]')?.textContent).toContain(
		'Sin aplicar los filtros del feed.'
	);
	const medios = target.querySelector('[aria-labelledby="medios-title"]');
	expect(medios?.textContent).toContain('Medios detectados');
	expect(medios?.textContent).not.toContain('Sin aplicar los filtros');
	const origen = target.querySelector('[aria-labelledby="origen-title"]')?.textContent ?? '';
	expect(origen).toContain('Noticias');
	expect(origen).toContain('200');
});

it('shows measured zero for an actual empty result', async () => {
	const data = dataFixture();
	data.mentions = { items: [], total: 0 };
	data.feedStats = { total: 0, by_source: {}, by_sentiment: { positive: 0, negative: 0, neutral: 0, none: 0 }, news_medium_count: 0, result_group_count: 0 };
	const target = await render(data);
	expect([...target.querySelectorAll('.stat-value')].map((node) => node.textContent)).toEqual([
		'0',
		'0',
		'0',
		'0'
	]);
	// v3 empty anatomy, filtered variant (the fixture carries a sentiment facet)
	expect(target.textContent).toContain('No hay menciones con estos filtros');
	expect(target.textContent).toContain('Limpiar filtros');
	expect(target.querySelector('.feed-empty a.button')?.getAttribute('href')).toBe('/feed');
	// period variant: no facets, only an empty range
	const bare = dataFixture();
	bare.mentions = { items: [], total: 0 };
	bare.feedStats = data.feedStats;
	bare.filters = { ...bare.filters, sentiment: '' };
	const periodTarget = await render(bare);
	expect(periodTarget.textContent).toContain('No hay menciones en este periodo');
	expect(periodTarget.textContent).toContain('Ver todo el periodo');
	expect(periodTarget.textContent).not.toContain('No disponible');
});

it('does not fall back to page groups when metrics are missing', async () => {
	const data = dataFixture();
	data.feedStats = null;
	const target = await render(data);
	expect(target.querySelectorAll('.feed-group')).toHaveLength(1);
	expect(target.querySelector('.feed-stats')?.textContent).not.toMatch(/\b40\b/);
	expect(target.querySelector('[role="status"]')?.textContent).toBe('Indicadores no disponibles.');
});

it('leaves cards and forms independent of metric changes', async () => {
	const first = await render();
	const data = dataFixture();
	data.feedStats = { ...data.feedStats!, news_medium_count: 3, result_group_count: 4 };
	const second = await render(data);
	expect(second.querySelector('.feed-list')?.outerHTML).toBe(first.querySelector('.feed-list')?.outerHTML);
	expect(second.querySelector('.pagination')?.outerHTML).toBe(first.querySelector('.pagination')?.outerHTML);
	expect(second.querySelector('[data-testid="feed-filter-main"]')?.outerHTML).toBe(first.querySelector('[data-testid="feed-filter-main"]')?.outerHTML);
});

it('renders full-result metrics while retaining one loaded card and publication pagination', async () => {
	const target = await render();
	expect([...target.querySelectorAll('.stat-value')].map((node) => node.textContent)).toEqual([
		'96',
		'63',
		'17',
		'1'
	]);
	expect(target.querySelectorAll('.feed-group')).toHaveLength(1);
	expect(target.textContent).toContain('Publicación sintética conservada');
	expect(target.querySelector('.feed-match-count')?.textContent).toContain('96 publicaciones encontradas');
	expect(target.querySelector('.page-status')?.textContent?.replace(/\s+/g, ' ')).toContain('Página 1 de 96');
	expect(target.querySelector('.feed-stats')?.textContent?.replace(/\s+/g, ' ')).toContain('Eventos y publicaciones sin evento en todos los resultados filtrados.');
	expect(target.querySelector('.feed-stats')?.textContent).not.toContain('esta página');
});

it('renders the v3 strip: four measured cards and the period reset link', async () => {
	const target = await render();
	const labels = [...target.querySelectorAll('.feed-stats .stat-top > span:not(.stat-icon)')].map(
		(node) => node.textContent?.trim()
	);
	expect(labels).toEqual([
		'Menciones en el feed',
		'Eventos',
		'Medios con noticias',
		'Fuentes con registros'
	]);
	// v3 stat anatomy: every card carries a toned icon tile (styles.css .stat-icon)
	const icons = [...target.querySelectorAll('.feed-stats .stat-icon')].map((node) =>
		node.className.replace('stat-icon ', '')
	);
	expect(icons).toEqual(['news', 'neutral', 'field', 'social']);
	const notes = [...target.querySelectorAll('.feed-stats .stat-note')].map((node) =>
		node.textContent?.replace(/\s+/g, ' ').trim()
	);
	expect(notes[0]).toBe('1 tipos de fuente');
	expect(target.querySelector('.feed-stats-reset')).toBeNull();
});

it('renders the v3 panel anatomy: toolbar, tone filter, rail and item rows', async () => {
	const target = await render();
	const markers = [
		'.feed-intro',
		'.feed-intro .feed-refresh-status',
		'.feed-stats .stat .stat-value',
		'.feed-content-grid',
		'.feed-main .feed-toolbar .panel-heading',
		'.tabs .tab.active',
		'.tone-filter .tone-filter-head',
		'.tone-filter .tone-choice.tone-negative',
		'.tone-filter .tone-bar',
		'.filterbar form[data-testid="feed-filter-main"] .search input',
		'.feed-match-count',
		'.feed-list .feed-group .feed-item',
		'.feed-item .feed-meta .source-badge',
		'.feed-item .feed-meta .tone-badge',
		'.feed-item .feed-meta .feed-time',
		'.feed-item .headline button.headline-button',
		'.feed-side-column .feed-period-panel #feed-period-preset',
		'.feed-aside .aside-panel .distribution-row',
		'.feed-aside .feed-source-list .feed-source-row',
		'.pagination .page-button'
	];
	for (const sel of markers) {
		expect(target.querySelector(sel), sel).not.toBeNull();
	}
	// v3 period panel: preset select first; custom range only when preset is custom
	const preset = target.querySelector<HTMLSelectElement>('#feed-period-preset');
	expect(preset?.value).toBe('all');
	expect(target.querySelector('.feed-date-controls')).toBeNull();
	const options = [...(preset?.options ?? [])].map((option) => option.textContent?.trim());
	expect(options).toEqual([
		'Hoy',
		'Ayer',
		'Ayer y hoy',
		'Últimos 10 días',
		'Último mes',
		'Personalizado',
		'Todo el periodo'
	]);
	// invented panels outside the v3 contract are gone
	expect(target.textContent).not.toContain('Histórico');
	expect(target.textContent).not.toContain('Seguimiento');
	// facet links apply in place (mockup behavior): no scroll-to-top on tap
	for (const link of target.querySelectorAll<HTMLAnchorElement>(
		'a.tone-choice, .tabs a.tab, .feed-source-list a.feed-source-row'
	)) {
		expect(link.hasAttribute('data-sveltekit-noscroll'), link.className).toBe(true);
	}
	// one card per loaded mention; the tone badge carries the active sentiment
	expect(target.querySelectorAll('.feed-item')).toHaveLength(1);
	expect(target.querySelector('.feed-item .tone-badge')?.textContent).toContain('Negativo');
	// the legacy two-panel/skin markers are gone
	expect(target.querySelector('.feed-filter-panel')).toBeNull();
	expect(target.querySelector('.result-line')).toBeNull();
});

it('opens the event expediente dialog from the chip and chains into the record', async () => {
	const target = await render();
	const chip = target.querySelector<HTMLButtonElement>('.feed-item .event-chip');
	expect(chip).toBeTruthy();

	chip!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await new Promise((resolve) => setTimeout(resolve, 30));
	await tick();

	const dialog = target.querySelector('dialog.event-detail');
	expect((dialog?.textContent ?? '').trim().length).toBeGreaterThan(0);
	const text = (dialog?.textContent ?? '').replace(/\s+/g, ' ');
	expect(text).toContain('Expediente #1');
	expect(text).toContain('Evento sintético');
	expect(text).toContain('2 menciones · 2 tipos de fuente. Conteo de registros, no de confirmaciones independientes.');
	expect(text).toContain('Fuentes y evidencias');
	expect(text).toContain('Leer registro original');

	// chaining: "Leer registro original" swaps to the record dialog
	const recordButton = [...(dialog?.querySelectorAll('button') ?? [])].find((b) =>
		(b.textContent ?? '').includes('Leer registro original')
	);
	recordButton!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await new Promise((resolve) => setTimeout(resolve, 30));
	await tick();

	expect((target.querySelector('dialog.event-detail')?.textContent ?? '').trim()).toBe('');
	const record = target.querySelector('dialog.mention-detail');
	expect((record?.textContent ?? '').replace(/\s+/g, ' ')).toContain('Detalle de la mención');
});

it('opens the mention detail dialog from a card', async () => {
	const target = await render();

	const button = target.querySelector<HTMLButtonElement>('.feed-item .headline-button');
	expect(button).toBeTruthy();
	button!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await new Promise((resolve) => setTimeout(resolve, 30));
	await tick();

	const dialog = target.querySelector('dialog.mention-detail');
	expect(dialog).toBeTruthy();
	const text = (dialog?.textContent ?? '').replace(/\s+/g, ' ');
	expect(text).toContain('Detalle de la mención');
	expect(text).toContain('Texto original');
	expect(text).toContain('Contenido capturado.');
	expect(text).toContain('Ir a la publicación');
	expect(/Ver evento #\d+|Todavía no forma un evento/.test(text)).toBe(true);
});

it('renders the mockup card foot: instant save toggle with cookie persistence', async () => {
	const target = await render();
	const foot = target.querySelector('.feed-item .feed-foot');
	expect(foot).not.toBeNull();
	expect(foot?.querySelector('.chips')).not.toBeNull();
	const button = foot?.querySelector<HTMLButtonElement>('.icon-button');
	expect(button?.getAttribute('aria-label')).toBe('Guardar noticia');
	expect(button?.getAttribute('aria-pressed')).toBe('false');

	button!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await tick();

	expect(button?.classList.contains('saved')).toBe(true);
	expect(button?.getAttribute('aria-label')).toBe('Quitar de guardados');
	expect(button?.getAttribute('aria-pressed')).toBe('true');
	expect(toast.message).toBe('Preferencia guardada en este navegador.');
	expect(document.cookie).toContain('mm_prefs=');
});

it('renders the Toaster outlet with role=status', async () => {
	const { mount: mountComponent } = await import('svelte');
	const Toaster = (await import('$lib/components/Toaster.svelte')).default;
	const host = document.createElement('div');
	document.body.appendChild(host);
	const instance = mountComponent(Toaster, { target: host });
	mounted.push(instance as never);
	toast.message = null;
	await tick();
	expect(host.querySelector('.toast')).toBeNull();

	toast.message = 'Preferencia guardada en este navegador.';
	await tick();
	const outlet = host.querySelector('.toast');
	expect(outlet?.textContent?.trim()).toBe('Preferencia guardada en este navegador.');
	expect(outlet?.getAttribute('role')).toBe('status');
	toast.message = null;
});

it('filters the loaded page under Guardadas and counts visible mentions', async () => {
	const data = dataFixture();
	const second = { ...data.mentions.items[0], id: 2, event_id: null, title: 'Segunda publicación suelta' };
	data.mentions = { items: [...data.mentions.items, second as Mention], total: 2 };
	data.prefs = { saved: [2], follow: [], seen: {} };
	const target = await render(data);
	await tick();

	const filter = target.querySelector<HTMLButtonElement>('[id="saved-filter"]');
	expect(filter?.textContent?.trim()).toBe('Guardadas');
	expect(filter?.getAttribute('aria-pressed')).toBe('false');
	expect(target.querySelector('#saved-filter svg')).not.toBeNull();

	filter!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await tick();

	expect(filter?.getAttribute('aria-pressed')).toBe('true');
	expect(filter?.textContent?.trim()).toBe('Ver todas');
	// solo la guardada visible: la del evento (sin marca) se filtra
	const heads = [...target.querySelectorAll('.feed-item .headline')].map((node) => node.textContent?.trim());
	expect(heads).toEqual(['Segunda publicación suelta']);
	expect(target.querySelector('.feed-match-count')?.textContent).toContain('1 publicaciones encontradas');
});

it('shows the filtered empty state when nothing saved matches', async () => {
	const data = dataFixture();
	data.mentions = { items: [], total: 0 };
	data.feedStats = { total: 0, by_source: {}, by_sentiment: { positive: 0, negative: 0, neutral: 0, none: 0 }, news_medium_count: 0, result_group_count: 0 };
	data.prefs = { saved: [9], follow: [], seen: {} };
	const target = await render(data);
	const filter = target.querySelector<HTMLButtonElement>('[id="saved-filter"]');
	filter!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await tick();
	expect(target.textContent).toContain('No hay menciones con estos filtros');
});

it('labels lone mentions, news authors and person chips per the mockup', async () => {
	const data = dataFixture();
	const lone = { ...data.mentions.items[0], id: 2, event_id: null };
	data.mentions = { items: [...data.mentions.items, lone as Mention], total: 2 };
	const target = await render(data);

	const chipRows = [...target.querySelectorAll('.feed-item .chips')];
	expect(chipRows).toHaveLength(2);
	// mención sin evento: chip individual en vez de evento
	expect(chipRows[1]?.querySelector('span.chip')?.textContent?.trim()).toBe('Mención individual');
	expect(chipRows[1]?.querySelector('.event-chip')).toBeNull();
	// autor news con prefijo y fallback verbatim
	expect(target.querySelector('.feed-item .feed-author')?.textContent?.trim()).toBe('Autor: No indicado');
	// persona: label mockup conservando el link a la ficha
	const personLink = target.querySelector('.feed-item .chips a');
	expect(personLink?.getAttribute('href')).toBe('/persons/3');
	expect(personLink?.textContent?.trim()).toBe('Persona: Ana López');
});

it('renders the focus panel with followed events, unread marker and window counts', async () => {
	const data = dataFixture();
	data.prefs = { saved: [], follow: [1], seen: {} };
	data.focusEvents = [{ id: 1, title: 'Evento sintético', mentions: 1, sourceKinds: 1 }];
	const target = await render(data);

	const panel = [...target.querySelectorAll('.feed-aside .aside-panel')].find((node) =>
		node.querySelector('h2')?.textContent?.trim() === 'Eventos en foco'
	);
	expect(panel).toBeTruthy();
	const link = panel?.querySelector<HTMLAnchorElement>('a.text-link');
	expect(link?.getAttribute('href')).toBe('/events');
	expect(link?.textContent?.trim()).toBe('Ver todos');

	const mini = panel?.querySelector<HTMLButtonElement>('button.event-mini');
	expect(mini?.querySelector('.mini-id')?.textContent).toContain('EVENTO #1');
	expect(mini?.querySelector('.mini-title')?.textContent?.trim()).toBe('Evento sintético');
	expect(mini?.querySelector('.event-unread')?.textContent?.trim()).toContain('Actualizado · sin ver');
	const count = mini?.querySelector('.mini-count')?.textContent?.replace(/\s+/g, ' ').trim();
	expect(count).toContain('1 menciones');
	expect(count).toContain('1 tipos de fuente');

	// abrir el expediente marca el evento como visto: el marker desaparece
	mini!.dispatchEvent(new MouseEvent('click', { bubbles: true }));
	await new Promise((resolve) => setTimeout(resolve, 30));
	await tick();
	expect((target.querySelector('dialog.event-detail')?.textContent ?? '')).toContain('Expediente #1');
	expect(mini?.querySelector('.event-unread')).toBeNull();
	expect(document.cookie).toContain('mm_prefs=');
});

it('renders the focus panel empty states verbatim', async () => {
	const data = dataFixture();
	data.prefs = { saved: [], follow: [], seen: {} };
	const none = await render(data);
	expect(none.textContent).toContain('Aún no sigues eventos. Puedes marcarlos en la página Eventos.');

	const quiet = dataFixture();
	quiet.prefs = { saved: [], follow: [1], seen: {} };
	quiet.focusEvents = [];
	const quietTarget = await render(quiet);
	expect(quietTarget.textContent).toContain('Sin menciones de eventos en foco en este periodo.');
});
