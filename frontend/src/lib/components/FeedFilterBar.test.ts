// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount, unmount } from 'svelte';
import type { Keyword } from '$lib/api';
import FeedFilterBar from './FeedFilterBar.svelte';

function keywordFixture(overrides: Partial<Keyword> = {}): Keyword {
	return {
		id: 3,
		text: 'nvidia',
		language: 'es',
		is_active: true,
		created_at: '2026-01-01T00:00:00Z',
		...overrides
	};
}

interface Filters {
	source: string;
	sentiment: string;
	keyword_id: string;
	political: string;
	since: string;
	until: string;
	q: string;
	limit: number;
}

function baseFilters(overrides: Partial<Filters> = {}): Filters {
	return {
		source: '',
		sentiment: '',
		keyword_id: '',
		political: '',
		since: '',
		until: '',
		q: '',
		limit: 50,
		...overrides
	};
}

const mounted: Array<{ instance: Record<string, unknown> }> = [];

function renderBar(props: {
	filters: Filters;
	sources?: string[];
	keywords?: Keyword[];
	resetHref?: string;
}): { host: HTMLElement } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(FeedFilterBar, {
		target,
		props: {
			sources: ['news_rss'],
			keywords: [],
			resetHref: '/feed',
			...props
		}
	});
	mounted.push({ instance });
	return { host: target };
}

function change(select: HTMLSelectElement, value: string) {
	select.value = value;
	select.dispatchEvent(new Event('change', { bubbles: true }));
}

afterEach(() => {
	for (const { instance } of mounted) unmount(instance as never);
	mounted.length = 0;
	document.body.innerHTML = '';
	vi.restoreAllMocks();
});

describe('FeedFilterBar', () => {
	it('keeps the GET form contract: every legacy param name is present', () => {
		const { host } = renderBar({ filters: baseFilters() });
		const form = host.querySelector('form');
		expect(form?.getAttribute('method')).toBe('get');

		for (const name of ['source', 'sentiment', 'keyword_id', 'political', 'since', 'until', 'q', 'limit']) {
			expect(host.querySelector(`[name="${name}"]`), `param ${name}`).not.toBeNull();
		}
	});

	it('renders source and sentiment as always-visible pill selects', () => {
		const { host } = renderBar({
			filters: baseFilters({ source: 'news_rss', sentiment: 'positive' })
		});

		const source = host.querySelector('#f-source') as HTMLSelectElement;
		const sentiment = host.querySelector('#f-sentiment') as HTMLSelectElement;
		expect(source).toBeInstanceOf(HTMLSelectElement);
		expect(sentiment).toBeInstanceOf(HTMLSelectElement);
		expect(source.selectedOptions[0]?.textContent).toContain('News RSS');
		expect(sentiment.value).toBe('positive');
		// Visible without opening the disclosure: pills sit outside <details>.
		expect(source.closest('details')).toBeNull();
		expect(sentiment.closest('details')).toBeNull();
		expect(sentiment.closest('details')).toBeNull();
	});

	it('auto-submits the form when a pill filter changes', async () => {
		const submit = vi.spyOn(HTMLFormElement.prototype, 'requestSubmit').mockReturnValue(undefined);
		const { host } = renderBar({ filters: baseFilters() });
		// bind:this lands in a scheduled effect: flush microtasks before acting,
		// mirroring how a real browser reaches the first user interaction.
		await new Promise((resolve) => setTimeout(resolve, 0));

		const form = host.querySelector('form') as HTMLFormElement;
		change(host.querySelector('#f-sentiment') as HTMLSelectElement, 'negative');

		expect(submit).toHaveBeenCalledTimes(1);
		expect(submit.mock.instances[0]).toBe(form);
	});

	it('folds keyword, political, dates, search and limit into a closed disclosure', () => {
		const { host } = renderBar({ filters: baseFilters() });

		const details = host.querySelector('details');
		expect(details).not.toBeNull();
		expect(details?.hasAttribute('open')).toBe(false);
		expect(details?.querySelector('summary')?.textContent).toContain('Más filtros');

		for (const id of ['f-keyword', 'f-q', 'f-limit']) {
			expect(details?.querySelector(`#${id}`), `advanced ${id}`).not.toBeNull();
		}
		expect(details?.querySelector('input[name="political"]')).not.toBeNull();
		expect(details?.querySelector('input[name="since"]')).not.toBeNull();
		expect(details?.querySelector('input[name="until"]')).not.toBeNull();
	});

	it('shows no count badge without active advanced filters', () => {
		const { host } = renderBar({ filters: baseFilters() });

		expect(host.querySelector('details summary span')).toBeNull();
	});

	it('counts active advanced filters in the summary badge', () => {
		const { host } = renderBar({
			filters: baseFilters({ keyword_id: '3', political: '1', q: 'gpu' })
		});

		const badge = host.querySelector('details summary span') as HTMLElement;
		expect(badge.textContent?.trim()).toBe('3');
		expect(badge.getAttribute('aria-label')).toContain('filtros avanzados');
	});

	it('ignores the pagination limit for the advanced count', () => {
		const { host } = renderBar({ filters: baseFilters({ limit: 200 }) });

		expect(host.querySelector('details summary span')).toBeNull();
	});

	it('keeps a no-JS submit button inside the disclosure', () => {
		const { host } = renderBar({ filters: baseFilters() });

		const submit = host.querySelector('details button[type="submit"]');
		expect(submit?.textContent).toContain('Aplicar');
	});

	it('resets every param through the subtle Limpiar link', () => {
		const { host } = renderBar({ filters: baseFilters({ q: 'x' }) });

		const link = host.querySelector('a') as HTMLAnchorElement;
		expect(link.textContent.trim()).toBe('Limpiar');
		expect(link.getAttribute('href')).toBe('/feed');
	});

	it('labels the pill selects for assistive tech', () => {
		const { host } = renderBar({ filters: baseFilters() });

		for (const id of ['f-source', 'f-sentiment']) {
			const select = host.querySelector(`#${id}`) as HTMLSelectElement;
			const label = host.querySelector(`label[for="${id}"]`);
			expect(label, `label for ${id}`).not.toBeNull();
			// Compact row: the label is visually hidden, not absent.
			expect(label?.classList.contains('sr-only')).toBe(true);
			expect(select.getAttribute('id')).toBe(id);
		}
	});
});
