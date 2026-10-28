// @vitest-environment jsdom
import { mount, unmount } from 'svelte';
import { afterEach, describe, expect, it } from 'vitest';

import type { PersonDetail, PersonSummary } from '$lib/api';

import PersonsPage from '../routes/persons/+page.svelte';
import PersonDetailPage from '../routes/persons/[id]/+page.svelte';

/**
 * Persons views (v3 «Panel de monitoreo»): directory panel with the
 * monogram/name/alias cell, plus the day-grouped mention timeline with
 * stamp/badges/quote. Copy stays «Actores»; aliases render as
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

function renderList(persons: PersonSummary[], q = '') {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(PersonsPage, {
		target,
		props: { params: {}, data: { persons, q }, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		root: target
	};
}

function renderDetail(personRow: PersonDetail) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(PersonDetailPage, {
		target,
		props: { params: { id: '1' }, data: { person: personRow }, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		root: target
	};
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

describe('persons list', () => {
	it('renders the v3 directory panel with monogram, alias line and counts', () => {
		const { text, root } = renderList([person(), person({ id: 2, name: 'Beto Lara', aliases: [] })]);

		expect(text()).toContain('Actores');
		expect(text()).toContain('Actores en seguimiento');
		expect(text()).toContain('También mencionado como: Mejía Ruiz');
		expect(root.querySelector('section.directory-panel')).toBeTruthy();
		expect(root.querySelector('.directory-header h2')).toBeTruthy();
		expect(root.querySelectorAll('.directory-monogram').length).toBe(2);
		const name = root.querySelector<HTMLAnchorElement>('a.directory-name');
		expect(name?.getAttribute('href')).toBe('/persons/1');
		expect(root.querySelectorAll('.directory-table th').length).toBe(5);
		expect(text()).toContain('Menciones');
		const count = root.querySelector('td[data-label="Menciones"] strong');
		expect(count?.textContent).toBe('7');
		const seen = root.querySelector('td[data-label="Última vez"] time');
		expect(seen?.getAttribute('datetime')).toBe('2026-10-27T21:30:00Z');
		expect(root.querySelector('.directory-disclaimer')).toBeTruthy();
	});

	it('keeps the search form and shows the empty state without a table', () => {
		const { text, root } = renderList([], 'rectoría');

		expect(root.querySelector('form[method="get"]')).toBeTruthy();
		const input = root.querySelector<HTMLInputElement>('input[name="q"]');
		expect(input?.value).toBe('rectoría');
		expect(root.querySelector('.person-empty .empty')).toBeTruthy();
		expect(root.querySelector('.directory-table')).toBeNull();
		expect(text()).toContain('Sin actores registrados');
	});
});

describe('persons detail', () => {
	it('renders the v3 record: eyebrow, meta and day-grouped timeline', () => {
		const { text, root } = renderDetail({
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

		expect(root.querySelector('.person-head .eyebrow')?.textContent).toBe('Actor');
		expect(text()).toContain('También mencionado como: Mejía Ruiz');
		const dts = [...root.querySelectorAll('.directory-detail-meta dt')].map((el) => el.textContent);
		expect(dts).toEqual(['Primera mención', 'Última mención']);

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
		const title = root.querySelector<HTMLAnchorElement>('.mention-timeline-content h4 a');
		expect(title?.getAttribute('href')).toBe('https://example.com/nota');
	});

	it('groups same-day mentions into a single day and keeps the empty state', () => {
		const sameDay = renderDetail({
			...person(),
			timeline: [timelineItem(), timelineItem({ mention_id: 12 })]
		});
		expect(sameDay.text()).toContain('2 menciones');
		expect(sameDay.root.querySelectorAll('.mention-day').length).toBe(1);
		expect(sameDay.root.querySelectorAll('.mention-timeline-item').length).toBe(2);

		const empty = renderDetail({ ...person(), timeline: [] });
		expect(empty.text()).toContain('Sin menciones registradas.');
		expect(empty.root.querySelector('.mention-timeline')).toBeNull();
	});
});
