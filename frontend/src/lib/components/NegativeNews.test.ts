// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';

import NegativeNews from './NegativeNews.svelte';
import type { Mention } from '$lib/api';

let nextId = 1;

/** Minimal Mention-like row; the component reads the feed-card fields. */
function mention(n: number): Mention {
	return {
		id: nextId++,
		keyword_id: null,
		source: 'news_rss',
		external_id: null,
		url: `https://a/${n}`,
		title: `Nota negativa ${n}`,
		summary: null,
		content: null,
		author: null,
		sentiment: 'negative',
		published_at: '2026-10-19T21:05:00Z',
		ingested_at: '2026-10-19T21:06:00Z',
		event_id: 100 + n,
		reach: null
	} as never;
}

let instance: Record<string, unknown> | undefined;

function render(mentions: Mention[]) {
	const target = document.createElement('div');
	document.body.append(target);
	instance = mount(NegativeNews, { target, props: { mentions } });
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

	it('renders each entry as the shared feed card (MentionCard)', () => {
		const host = render([mention(1)]);
		const panel = host.querySelector('.negative-summary')!;
		expect(panel.querySelector('.negative-count')?.textContent?.replace(/\s+/g, ' ')).toContain(
			'1 noticia'
		);
		// The card anatomy comes from MentionCard/NewsEntry, not a local copy.
		const card = panel.querySelector('.feed-item')!;
		expect(card.querySelector('.feed-meta')).toBeTruthy();
		expect(card.textContent).toContain('Nota negativa 1');
		const link = card.querySelector('.headline a') as HTMLAnchorElement | null;
		expect(link?.getAttribute('href')).toBe('https://a/1');
	});

	it('caps the list at three and discloses the total', () => {
		const host = render([1, 2, 3, 4, 5].map(mention));
		expect(host.querySelectorAll('.feed-item').length).toBe(3);
		const note = host.querySelector('.negative-context')?.textContent?.replace(/\s+/g, ' ');
		expect(note).toContain('Se muestran 3 de 5 noticias negativas');
		expect(host.querySelector('.negative-count')?.textContent).toContain('5');
	});
});
