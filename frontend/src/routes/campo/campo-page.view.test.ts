// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, tick, unmount } from 'svelte';

import CampoPage from './+page.svelte';
import type { PageProps } from './$types';
import type { FieldReportRecord } from '$lib/api';

function report(over: Partial<FieldReportRecord> & Pick<FieldReportRecord, 'id' | 'status'>): FieldReportRecord {
	return {
		operator_id: 7,
		title: null,
		content: null,
		place: null,
		happened_at: null,
		review_note: null,
		enrichment: null,
		mention_id: null,
		created_at: '2026-10-27T15:30:00+00:00',
		published_at: null,
		...over
	};
}

function baseData() {
	return {
		pending: [
			report({
				id: 1,
				status: 'review',
				title: 'Bloqueo en la entrada norte',
				content: 'Vecinos reportan una barricada desde las 8:00.',
				place: 'Entrada norte'
			})
		],
		recent: [
			report({
				id: 2,
				status: 'published',
				title: 'Pavimentación terminada',
				content: 'La obra concluyó el viernes.',
				place: 'Sur',
				published_at: '2026-10-27T18:00:00+00:00'
			}),
			report({
				id: 3,
				status: 'rejected',
				title: 'Ruido en la feria',
				content: 'Queja por amplicadores después de medianoche.',
				review_note: 'Fuera de cobertura'
			})
		]
	};
}

const mounted: unknown[] = [];

function renderPage(data: Record<string, unknown>, form: Record<string, unknown> | null = null) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(CampoPage, {
		target,
		props: {
			data: data as PageProps['data'],
			form: form as PageProps['form']
		}
	});
	mounted.push(instance);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		query: (selector: string) => target.querySelector(selector),
		queryAll: (selector: string) => [...target.querySelectorAll(selector)],
		target,
		instance
	};
}

afterEach(() => {
	while (mounted.length) {
		const instance = mounted.pop();
		if (instance) unmount(instance as never);
	}
});

describe('campo inbox view', () => {
	it('renders the inbox skeleton with status counts and preserved operadores link', () => {
		const page = renderPage(baseData());
		const text = page.text();
		expect(text).toContain('Bandeja de reportes');
		expect(text).toContain('Por revisar1');
		expect(text).toContain('Publicado1');
		expect(text).toContain('Descartado1');
		expect(text).toContain('Recepción');
		expect(page.query('table.field-inbox-table')).not.toBeNull();
		const link = page.query('a[href="/campo/operadores"]');
		expect(link?.textContent?.trim()).toBe('Listado de operadores');
		// estados reales del modelo, mapeados 1:1
		expect(page.query('.field-inbox-state.review')?.textContent?.trim()).toBe('Por revisar');
	});

	it('filters rows from the status tabs', async () => {
		const page = renderPage(baseData());
		const tabs = page.queryAll('.field-inbox-status button');
		expect(tabs).toHaveLength(3);
		(tabs[1] as HTMLButtonElement).click();
		await tick();
		const text = page.text();
		expect(text).toContain('Pavimentación terminada');
		expect(text).not.toContain('Bloqueo en la entrada norte');
		expect(page.query('.field-inbox-state.published')).not.toBeNull();
	});

	it('filters by the search box and shows the empty state', async () => {
		const page = renderPage(baseData());
		const input = page.query('.field-search input') as HTMLInputElement;
		input.value = 'imposible de encontrar';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		expect(page.text()).toContain('Sin resultados');
		expect(page.text()).toContain('No hay registros en esta selección');
	});

	it('opens the review dialog with the preserved approval actions', async () => {
		const page = renderPage(baseData());
		const rowButton = page.queryAll('table .button')[0] as HTMLButtonElement;
		expect(rowButton?.textContent?.trim()).toBe('Revisar');
		rowButton.click();
		await tick();
		const dialog = page.query('dialog');
		expect(dialog).not.toBeNull();
		expect(page.text()).toContain('Reporte #1');
		expect(page.text()).toContain('Reporte original');
		expect(page.query('button[formaction="?/approve"]')?.textContent?.trim()).toBe(
			'Publicar en el Feed'
		);
		expect(page.query('button[formaction="?/reject"]')?.textContent?.trim()).toBe('Descartar');
		expect(page.query('.field-form input[name="id"]')).not.toBeNull();
		expect(page.query('.field-form textarea[name="note"]')).not.toBeNull();
	});

	it('shows the feed link for published reports', async () => {
		const page = renderPage(baseData());
		const tabs = page.queryAll('.field-inbox-status button');
		(tabs[1] as HTMLButtonElement).click();
		await tick();
		(page.queryAll('table .button')[0] as HTMLButtonElement).click();
		await tick();
		const link = page.query('.field-report-dialog a[href="/feed?source=field_report"]');
		expect(link?.textContent?.trim()).toBe('Ver en el feed');
	});
});
