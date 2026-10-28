// @vitest-environment jsdom
import { mount, tick, unmount } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';
import Feed from '../routes/feed/+page.svelte';
import type { PageProps } from '../routes/feed/$types';

vi.mock('$app/state', () => ({ page: { url: new URL('http://localhost/feed?sentiment=negative&limit=1') } }));
vi.mock('$app/navigation', () => ({ invalidateAll: vi.fn() }));

const mounted: ReturnType<typeof mount>[] = [];
function dataFixture(): PageProps['data'] {
	return {
		mentions: { items: [{ id: 1, source: 'news_rss', title: 'Publicación sintética conservada', url: 'https://alpha.example/1', keyword_id: null, external_id: null, content: 'Contenido capturado.', summary: null, author: null, lang: 'es', published_at: '2026-10-14T12:00:00Z', ingested_at: '2026-10-14T12:00:00Z', sentiment: 'negative', sentiment_score: 0.2, reach: null, classifications: [], event_id: 1 }], total: 96 },
		keywords: [], digest: null,
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
	for (const id of ['medios-title', 'origen-title']) {
		expect(target.querySelector(`[aria-labelledby="${id}"]`)?.textContent).toContain(
			'Sin aplicar los filtros del feed.'
		);
	}
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
	expect(target.textContent).toContain('Sin resultados');
	expect(target.textContent).not.toContain('No disponible');
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
	const labels = [...target.querySelectorAll('.feed-stats .stat-top span')].map((node) =>
		node.textContent?.trim()
	);
	expect(labels).toEqual([
		'Menciones en el feed',
		'Eventos',
		'Medios con noticias',
		'Fuentes con registros'
	]);
	const notes = [...target.querySelectorAll('.feed-stats .stat-note')].map((node) =>
		node.textContent?.replace(/\s+/g, ' ').trim()
	);
	expect(notes[0]).toBe('1 tipos de fuente');
	expect(target.querySelector('.feed-stats-reset')?.textContent?.trim()).toBe(
		'Ver todo el periodo'
	);
	// the reset drops every facet, dates included (mockup data-reset behavior)
	expect(target.querySelector('.feed-stats-reset')?.getAttribute('href')).toBe('/feed');
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
		'.keyword-row .keyword-chip',
		'.feed-match-count',
		'.feed-list .feed-group .feed-item',
		'.feed-item .feed-meta .source-badge',
		'.feed-item .feed-meta .tone-badge',
		'.feed-item .feed-meta .feed-time',
		'.feed-item .headline a',
		'.feed-side-column .feed-period-panel .feed-date-controls',
		'.feed-aside .aside-panel .distribution-row',
		'.feed-aside .feed-source-list .feed-source-row',
		'.pagination .page-button'
	];
	for (const sel of markers) {
		expect(target.querySelector(sel), sel).not.toBeNull();
	}
	// one card per loaded mention; the tone badge carries the active sentiment
	expect(target.querySelectorAll('.feed-item')).toHaveLength(1);
	expect(target.querySelector('.feed-item .tone-badge')?.textContent).toContain('Negativo');
	// the legacy two-panel/skin markers are gone
	expect(target.querySelector('.feed-filter-panel')).toBeNull();
	expect(target.querySelector('.result-line')).toBeNull();
});
