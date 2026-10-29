// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';
import type { EventSummary } from '$lib/api';
import EventCard from './EventCard.svelte';

function eventFixture(overrides: Partial<EventSummary> = {}): EventSummary {
	return {
		id: 5,
		title: 'Anuncio de inversión',
		mention_count: 4,
		source_count: 2,
		summary: 'Varias casas financieras recogieron el anuncio.',
		first_seen_at: '2026-10-01T08:00:00Z',
		last_seen_at: '2026-10-02T17:30:00Z',
		...overrides
	};
}

const mounted: Array<{ instance: Record<string, unknown> }> = [];

function renderCard(event: EventSummary): { card: HTMLElement } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(EventCard, { target, props: { event } });
	mounted.push({ instance });
	return { card: target.querySelector('article') as HTMLElement };
}

function footerText(card: HTMLElement): string {
	return (card.querySelector('.event-card-footer')?.textContent ?? '')
		.replace(/\s+/g, ' ')
		.trim();
}

afterEach(() => {
	for (const { instance } of mounted) unmount(instance as never);
	mounted.length = 0;
	document.body.innerHTML = '';
});

describe('EventCard', () => {
	it('renders the v3 anatomy: mini-id, headline link and footer', () => {
		const { card } = renderCard(eventFixture());

		expect(card.classList.contains('event-card')).toBe(true);
		expect(card.querySelector('.mini-id')?.textContent).toContain('EVENTO #5');
		const title = card.querySelector('h3.headline a') as HTMLAnchorElement | null;
		expect(title).not.toBeNull();
		expect(card.querySelector('.event-card-footer')).not.toBeNull();
		// The v3 card carries no timestamp row; dates live on the detail page.
		expect(card.querySelector('time')).toBeNull();
	});

	it('links the title to the event detail page', () => {
		const { card } = renderCard(eventFixture());

		const link = card.querySelector('h3 a[href="/events/5"]') as HTMLAnchorElement;
		expect(link).not.toBeNull();
		expect(link.textContent).toContain('Anuncio de inversión');
	});

	it('shows mention and source counts in the footer', () => {
		const { card } = renderCard(eventFixture());

		expect(footerText(card)).toBe('4 menciones · 2 fuentes');
	});

	it('titles the source count as channel types, keeping the visible word', () => {
		const { card } = renderCard(eventFixture());

		const source = card.querySelector('.event-card-footer span[title]');
		expect(source?.getAttribute('title')).toBe('2 tipos de canal con registros');
		expect(source?.textContent?.replace(/\s+/g, ' ').trim()).toBe('2 fuentes');
	});

	it('uses singular wording for a lone mention', () => {
		const { card } = renderCard(eventFixture({ mention_count: 1, source_count: 1 }));

		expect(footerText(card)).toBe('1 mención · 1 fuente');
	});

	it('renders the summary when present', () => {
		const { card } = renderCard(eventFixture());

		expect(card.textContent).toContain('Varias casas financieras recogieron el anuncio.');
	});

	it('omits the summary paragraph when absent', () => {
		const { card } = renderCard(eventFixture({ summary: null }));

		expect(card.querySelector('p.event-summary')).toBeNull();
	});
});
