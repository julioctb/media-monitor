// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';

import RevisionesPage from './+page.svelte';
import type { PageProps } from './$types';

type RevisionsData = {
	days: { summary_date: string; count: number; last_at: string }[];
	selectedDay: string | null;
	revisions: {
		seq: number;
		summary_date: string;
		narrative: string;
		mode: string;
		created_at: string;
	}[];
};

function baseData(): RevisionsData {
	return {
		days: [
			{ summary_date: '2026-10-23', count: 2, last_at: '2026-10-23T21:00:00Z' },
			{ summary_date: '2026-10-22', count: 3, last_at: '2026-10-22T21:00:00Z' }
		],
		selectedDay: '2026-10-23',
		revisions: [
			{
				seq: 1,
				summary_date: '2026-10-23',
				narrative: 'Primera narrativa del día.',
				mode: 'heuristic',
				created_at: '2026-10-23T08:00:00Z'
			},
			{
				seq: 2,
				summary_date: '2026-10-23',
				narrative: 'La BUAP amaneció con dos frentes de tensión laboral.',
				mode: 'llm',
				created_at: '2026-10-23T21:00:00Z'
			}
		]
	};
}

const mounted: Record<string, unknown>[] = [];

function renderPage(data: RevisionsData, form: Record<string, unknown> | null = null) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(RevisionesPage, {
		target,
		props: {
			data: data as PageProps['data'],
			form: form as PageProps['form']
		}
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		container: target
	};
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

describe('Revisiones page', () => {
	it('lists the days with counts and every revision of the selected day', () => {
		const { container, text } = renderPage(baseData());
		const dayLinks = [...container.querySelectorAll('.revisions-days a')];
		expect(dayLinks.length).toBe(2);
		expect(dayLinks[0].getAttribute('aria-current')).toBe('page');
		expect(text()).toContain('23 de octubre de 2026');
		const cards = [...container.querySelectorAll('.revision-card')];
		expect(cards.length).toBe(2);
		expect(cards[0].textContent).toContain('#1');
		expect(cards[1].textContent).toContain('La BUAP amaneció');
		// Every card offers restore with its day+seq bound.
		const forms = [...container.querySelectorAll('form')];
		expect(forms.length).toBe(2);
		const hidden = forms[1].querySelector('input[name="seq"]') as HTMLInputElement;
		expect(hidden.value).toBe('2');
	});

	it('shows the empty state without history', () => {
		const { text } = renderPage({ days: [], selectedDay: '', revisions: [] });
		expect(text()).toContain('Sin revisiones registradas');
	});

	it('surfaces the restore result', () => {
		const { text } = renderPage(baseData(), { ok: true, message: 'Versión 1 aplicada.' });
		expect(text()).toContain('Versión 1 aplicada.');
	});
});
