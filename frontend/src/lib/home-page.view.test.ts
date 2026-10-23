// @vitest-environment jsdom
import { mount, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { DailySummary } from '$lib/api';

import type { PageProps } from '../routes/$types';

import HomePage from '../routes/+page.svelte';

/**
 * Home page view (digest v2): a day without a generated digest must keep
 * the page structure (header, sintesis, resumen general, cobertura) under
 * placeholder states instead of collapsing to a single empty legend.
 */

const mounted: Array<Record<string, unknown>> = [];

type HomeData = PageProps['data'];

function renderPage(data: HomeData): { text: () => string } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(HomePage, {
		target,
		props: { params: {}, data, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	// Markup wraps lines: collapse whitespace so copy asserts survive reflows.
	return { text: () => (target.textContent ?? '').replace(/\s+/g, ' ') };
}

function emptyDayData(): HomeData {
	return {
		day: '2026-10-23',
		before: null,
		summary: null,
		latest_updated_at: '2026-10-22T21:30:00Z',
		days: [],
		olderBefore: null,
		tones: null,
		keywordCounts: [],
		negativeEvents: [],
		liveCoverage: null,
		persons: [],
		keywords: [],
		digestHours: [21],
		sourcesCount: 3,
		socialLabels: {}
	};
}

function summaryFixture(): DailySummary {
	return {
		id: 1,
		client_id: 1,
		summary_date: '2026-10-23',
		content: { schema: 2, coverage: { total: 0 }, noticias: [], plain_text: 'texto plano' },
		narrative: 'Narrativa editorial del día.',
		mode: 'llm',
		created_at: '2026-10-23T21:00:00Z',
		updated_at: '2026-10-23T21:00:00Z'
	};
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

const PLACEHOLDER = 'En espera de generar el resumen del día';

it('keeps the page structure with placeholders when the digest is missing', () => {
	const { text } = renderPage(emptyDayData());

	// Header + sintesis wait state.
	expect(text()).toContain('Resumen diario / BUAP');
	expect(text()).toContain('Sintesis del día');
	expect(text()).toContain(PLACEHOLDER);
	expect(text()).toContain('En espera del primer corte del día');

	// The v2 skeleton stays in place: resumen general boxes + sidebar.
	expect(text()).toContain('Resumen general');
	expect(text()).toContain('Cobertura del día');
	expect(text()).toContain('Historial');

	// Old single-legend empty state is gone.
	expect(text()).not.toContain('Todavía no se genera el resumen del día');
});

it('renders the narrative and hides the placeholder once the digest exists', () => {
	const data = { ...emptyDayData(), summary: summaryFixture() };
	const { text } = renderPage(data);

	expect(text()).toContain('Narrativa editorial del día.');
	expect(text()).not.toContain(PLACEHOLDER);
	expect(text()).toContain('Interpretación actualizada a las');
});
