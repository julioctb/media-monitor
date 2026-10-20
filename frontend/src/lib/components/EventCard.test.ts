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

afterEach(() => {
	for (const { instance } of mounted) unmount(instance as never);
	mounted.length = 0;
	document.body.innerHTML = '';
});

describe('EventCard', () => {
	it('links the title to the event detail page', () => {
		const { card } = renderCard(eventFixture());

		const link = card.querySelector('h2 a[href="/events/5"]') as HTMLAnchorElement;
		expect(link).not.toBeNull();
		expect(link.textContent).toContain('Anuncio de inversión');
	});

	it('shows mention and source counts', () => {
		const { card } = renderCard(eventFixture());

		expect(card.textContent).toContain('4 menciones');
		expect(card.textContent).toContain('2 fuentes');
	});

	it('uses singular wording for a lone mention', () => {
		const { card } = renderCard(eventFixture({ mention_count: 1, source_count: 1 }));

		expect(card.textContent).toContain('1 mención');
		expect(card.textContent).toContain('1 fuente');
	});

	it('renders the summary when present', () => {
		const { card } = renderCard(eventFixture());

		expect(card.textContent).toContain('Varias casas financieras recogieron el anuncio.');
	});

	it('omits the summary paragraph when absent', () => {
		const { card } = renderCard(eventFixture({ summary: null }));

		expect(card.querySelector('p.event-summary')).toBeNull();
	});

	it('timestamps first and last sight', () => {
		const { card } = renderCard(eventFixture());

		const times = card.querySelectorAll('time');
		const datetimes = Array.from(times).map((t) => t.getAttribute('datetime'));
		expect(datetimes).toContain('2026-10-01T08:00:00Z');
		expect(datetimes).toContain('2026-10-02T17:30:00Z');
	});
});
