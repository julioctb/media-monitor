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
	expect([...target.querySelectorAll('.intro-stat-value')].map((node) => node.textContent)).toEqual(['No disponible', 'No disponible']);
	expect(target.querySelector('[role="status"]')?.textContent).toContain(data.feedStatsError);
	expect(target.querySelectorAll('.feed-group')).toHaveLength(1);
	expect(target.querySelector('.result-line')?.textContent).toContain('96 publicaciones encontradas');
	expect(target.querySelector('a.page-button')?.textContent).toContain('Siguiente');
});

it('labels global navigation separately from filtered-result indicators', async () => {
	const target = await render();
	for (const id of ['medios-title', 'estado-title']) {
		expect(target.querySelector(`[aria-labelledby="${id}"]`)?.textContent).toContain('Sin aplicar los filtros del feed.');
	}
	expect(target.querySelector('[aria-labelledby="estado-title"]')?.textContent).toContain('200 registros.');
});

it('shows measured zero for an actual empty result', async () => {
	const data = dataFixture();
	data.mentions = { items: [], total: 0 };
	data.feedStats = { total: 0, by_source: {}, by_sentiment: { positive: 0, negative: 0, neutral: 0, none: 0 }, news_medium_count: 0, result_group_count: 0 };
	const target = await render(data);
	expect([...target.querySelectorAll('.intro-stat-value')].map((node) => node.textContent)).toEqual(['0', '0']);
	expect(target.textContent).toContain('Sin resultados');
	expect(target.textContent).not.toContain('No disponible');
});

it('does not fall back to page groups when metrics are missing', async () => {
	const data = dataFixture();
	data.feedStats = null;
	const target = await render(data);
	expect(target.querySelectorAll('.feed-group')).toHaveLength(1);
	expect(target.querySelector('.intro-stats')?.textContent).not.toMatch(/\b40\b/);
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
	expect([...target.querySelectorAll('.intro-stat-value')].map((node) => node.textContent)).toEqual(['17', '63']);
	expect(target.querySelectorAll('.feed-group')).toHaveLength(1);
	expect(target.textContent).toContain('Publicación sintética conservada');
	expect(target.querySelector('.result-line')?.textContent).toContain('96 publicaciones encontradas');
	expect(target.querySelector('.page-status')?.textContent?.replace(/\s+/g, ' ')).toContain('Página 1 de 96');
	expect(target.querySelector('.intro-stats')?.textContent?.replace(/\s+/g, ' ')).toContain('Eventos y publicaciones sin evento en todos los resultados filtrados.');
	expect(target.querySelector('.intro-stats')?.textContent).not.toContain('esta página');
});
