// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';

import NegativeNews from './NegativeNews.svelte';
import type { NegativeNewsItem } from '$lib/digest-stats';

function item(n: number): NegativeNewsItem {
	return {
		event_id: 100 + n,
		title: `Nota negativa ${n}`,
		source: 'news_rss',
		published_at: '2026-10-19T21:05:00Z'
	};
}

let instance: Record<string, unknown> | undefined;

function render(items: NegativeNewsItem[], day = '2026-10-19') {
	const target = document.createElement('div');
	document.body.append(target);
	instance = mount(NegativeNews, { target, props: { items, day } });
	return target;
}

afterEach(() => {
	if (instance) void unmount(instance as never);
	instance = undefined;
});

describe('NegativeNews', () => {
	it('renders nothing without negative events', () => {
		expect(render([]).querySelector('.negative-summary')).toBeNull();
	});

	it('shows source, long date and the day-filtered feed link', () => {
		const host = render([item(1)]);
        const panel = host.querySelector('.negative-summary')!;
		expect(panel.querySelector('.negative-count')?.textContent?.replace(/\s+/g, ' ')).toContain('1 noticia');
		const source = panel.querySelector('.negative-source')?.textContent?.replace(/\s+/g, ' ');
		expect(source).toContain('News RSS');
		expect(source).toContain('19 de octubre de 2026');
		const link = panel.querySelector('a') as HTMLAnchorElement;
		expect(link.getAttribute('href')).toBe('/feed?since=2026-10-19&until=2026-10-19');
		expect(link.textContent).toContain('Nota negativa 1');
	});

	it('caps the list at three and discloses the total', () => {
		const host = render([1, 2, 3, 4, 5].map(item));
		expect(host.querySelectorAll('li').length).toBe(3);
		const note = host.querySelector('.negative-context')?.textContent?.replace(/\s+/g, ' ');
		expect(note).toContain('Se muestran 3 de 5 noticias negativas');
		expect(host.querySelector('.negative-count')?.textContent).toContain('5');
	});
});
