// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';
import type { Mention } from '$lib/api';
import MentionCard from './MentionCard.svelte';

function mentionFixture(overrides: Partial<Mention> = {}): Mention {
	return {
		id: 7,
		keyword_id: null,
		source: 'news_rss',
		external_id: null,
		url: 'https://example.com/nota',
		title: 'Una nota relevante',
		content: 'El texto del artículo.',
		author: null,
		lang: 'es',
		published_at: '2026-10-01T12:00:00Z',
		ingested_at: '2026-10-01T12:05:00Z',
		sentiment: 'positive',
		sentiment_score: 0.9,
		summary: null,
		reach: null,
		classifications: [],
		...overrides
	};
}

interface CardProps {
	mention: Mention;
	event?: { id: number; title: string } | null;
	keywordLabel?: string | null;
}

const mounted: Array<{ instance: Record<string, unknown> }> = [];

function renderCard(props: CardProps): { card: HTMLElement } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(MentionCard, { target, props });
	mounted.push({ instance });
	// Svelte 5 renders the article as the only element child of the target
	// (the rest is a comment anchor).
	return { card: target.querySelector('article') as HTMLElement };
}

afterEach(() => {
	for (const { instance } of mounted) unmount(instance as never);
	mounted.length = 0;
	document.body.innerHTML = '';
});

describe('MentionCard', () => {
	it('links the headline to the source with an accessible label', () => {
		const { card } = renderCard({ mention: mentionFixture() });

		const link = card.querySelector('a[target="_blank"]') as HTMLAnchorElement;
		expect(link.getAttribute('href')).toBe('https://example.com/nota');
		expect(link.getAttribute('rel')).toContain('noopener');
		expect(link.textContent).toContain('Una nota relevante');
		expect(link.getAttribute('aria-label')).toContain('abre en una pestaña nueva');
	});

	it('falls back to the URL as the headline without a title', () => {
		const { card } = renderCard({ mention: mentionFixture({ title: null }) });

		const link = card.querySelector('a[target="_blank"]') as HTMLAnchorElement;
		expect(link?.textContent?.trim()).toBe('https://example.com/nota');
	});

	it('shows the source and sentiment badges without prefixes', () => {
		const { card } = renderCard({ mention: mentionFixture() });

		expect(card.textContent).toContain('News RSS');
		expect(card.textContent).not.toContain('Fuente:');
		expect(card.querySelector('.item-top .sentiment')?.textContent).toContain('Positivo');
		expect(card.querySelector('.sentiment.positive')).not.toBeNull();
	});

	it('labels unclassified sentiment explicitly', () => {
		const { card } = renderCard({ mention: mentionFixture({ sentiment: null }) });

		expect(card.textContent).toContain('Sin clasificar');
	});

	it('omits the enrichment block when there is no summary', () => {
		const { card } = renderCard({ mention: mentionFixture({ summary: null }) });

		expect(card.querySelector('details')).toBeNull();
	});

	it('hides the enrichment summary behind an expandable details', () => {
		const { card } = renderCard({
			mention: mentionFixture({ summary: 'La nota vincula al anuncio con la reforma.' })
		});

		const details = card.querySelector('details');
		expect(details).not.toBeNull();
		expect(details?.querySelector('summary')?.textContent).toContain('Resumen');
		expect(details?.textContent).toContain('La nota vincula al anuncio con la reforma.');
		// Collapsed by default: content is there, the disclosure is shut.
		expect(details?.hasAttribute('open')).toBe(false);
	});

	it('renders the event chip as a link when the event is resolved', () => {
		const { card } = renderCard({
			mention: mentionFixture(),
			event: { id: 3, title: 'Anuncio de reforma' }
		});

		const chip = card.querySelector('a[href="/events/3"]');
		expect(chip?.textContent).toContain('Anuncio de reforma');
	});

	it('renders no event chip without event context', () => {
		const { card } = renderCard({ mention: mentionFixture() });

		expect(card.querySelector('a[href^="/events/"]')).toBeNull();
	});

	it('shows the classification badges', () => {
		const { card } = renderCard({
			mention: mentionFixture({
				classifications: [
					{ classifier: 'political', label: 'political', score: 0.8 },
					{ classifier: 'topic', label: 'economy', score: 0.7 }
				]
			})
		});

		expect(card.textContent).toContain('Política');
		expect(card.textContent).toContain('Economía');
	});

	it('hides the No política badge: only the positive match renders', () => {
		const { card } = renderCard({
			mention: mentionFixture({
				classifications: [
					{ classifier: 'political', label: 'not_political', score: 0.7 },
					{ classifier: 'topic', label: 'academic', score: 0.9 }
				]
			})
		});

		expect(card.textContent).not.toContain('No política');
		expect(card.textContent).not.toContain('Política');
		// The clearer classification still shows.
		expect(card.textContent).toContain('Academia');
	});

	it('renders the person chips as links to the person page', () => {
		const { card } = renderCard({
			mention: mentionFixture({
				persons: [
					{ id: 12, name: 'Lilia Cedillo' },
					{ id: 13, name: 'Margarito Rojas' }
				]
			} as never)
		});

		const chips = [...card.querySelectorAll('a[href="/persons/12"]')];
		expect(chips).toHaveLength(1);
		expect(chips[0]?.textContent).toContain('Lilia Cedillo');
		expect(card.querySelector('a[href="/persons/13"]')?.textContent).toContain('Margarito Rojas');
	});

	it('renders no person chips without linked persons', () => {
		const { card } = renderCard({ mention: mentionFixture() });

		expect(card.querySelector('a[href^="/persons/"]')).toBeNull();
	});

	it('marks the ingest-date fallback with an asterisk', () => {
		const { card } = renderCard({ mention: mentionFixture({ published_at: null }) });

		const time = card.querySelector('time');
		expect(time?.getAttribute('datetime')).toBe('2026-10-01T12:05:00Z');
		expect(card.textContent).toMatch(/\*/);
	});

	it('shows the keyword label only when provided', () => {
		const bare = renderCard({ mention: mentionFixture() });
		expect(bare.card.textContent).not.toContain('Palabra clave');

		const labeled = renderCard({
			mention: mentionFixture({ id: 8, keyword_id: 2 }),
			keywordLabel: 'Nvidia'
		});
		expect(labeled.card.textContent).toContain('Palabra clave: Nvidia');
	});
});
