// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, tick, unmount } from 'svelte';

import OperadoresPage from './+page.svelte';
import type { PageProps } from './$types';
import type { FieldOperatorRecord } from '$lib/api';

type OperatorRow = FieldOperatorRecord & { last_report_at: string | null };

function operator(over: Partial<OperatorRow> & Pick<OperatorRow, 'id' | 'display_name'>): OperatorRow {
	return {
		telegram_user_id: null,
		phone: null,
		active: true,
		invited_at: null,
		accepted_at: null,
		last_report_at: null,
		...over
	};
}

function baseData() {
	return {
		operators: [
			operator({
				id: 1,
				display_name: 'Ana Reyes',
				phone: '52 222 111 0000',
				telegram_user_id: 9001,
				last_report_at: '2026-10-27T15:30:00+00:00'
			}),
			operator({
				id: 2,
				display_name: 'Beto López',
				active: false,
				invited_at: '2026-10-26T10:00:00+00:00'
			})
		]
	};
}

const mounted: unknown[] = [];

function renderPage(data: Record<string, unknown>, form: Record<string, unknown> | null = null) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(OperadoresPage, {
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

describe('operadores directory view', () => {
	it('renders the mockup table with estado, último reporte and Gestionar', () => {
		const page = renderPage(baseData());
		expect(page.query('.operators-view table.field-table')).not.toBeNull();
		expect(page.text()).toContain('Directorio de operadores de campo');
		const headers = page.queryAll('thead th').map((th) => th.textContent?.trim());
		expect(headers).toEqual([
			'Nombre',
			'Teléfono',
			'ID de Telegram',
			'Estado',
			'Último reporte',
			'Acciones'
		]);
		// Monograma + nombre, badge de estado binario y última recepción.
		const monogram = page.query('.field-operator-monogram');
		expect(monogram?.textContent?.trim()).toBe('AR');
		expect(page.queryAll('.field-operator-status.is-active')).toHaveLength(1);
		expect(page.query('.field-operator-status.is-inactive')?.textContent?.trim()).toBe('Inactivo');
		expect(page.text()).toContain('27/10/2026');
		expect(page.text()).toContain('Sin reportes');
		expect(page.queryAll('tbody button.button')).toHaveLength(2);
		expect(page.queryAll('tbody button.button')[0]?.textContent?.trim()).toBe('Gestionar');
		// Sin pseudónimo en el modelo: la columna del mockup se omite.
		expect(page.text()).not.toContain('Pseudónimo');
	});

	it('gestionar reveals the row actions and keeps the forms bound to the row', async () => {
		const page = renderPage(baseData());
		const manage = () => page.queryAll('tbody td button.button')[0] as HTMLButtonElement;
		expect(manage().getAttribute('aria-expanded')).toBe('false');
		manage().click();
		await tick();
		expect(manage().getAttribute('aria-expanded')).toBe('true');
		const panel = page.query('.field-operator-manage-row');
		expect(panel).not.toBeNull();
		// Operador 1 activo: desactivar + invitar, con su id conservado.
		expect(page.query('.field-operator-manage-row form[action="?/deactivate"]')).not.toBeNull();
		expect(page.query('.field-operator-manage-row form[action="?/invite"]')).not.toBeNull();
		expect(page.query('.field-operator-manage-row input[name="id"]')?.getAttribute('value')).toBe('1');
		expect(panel?.textContent).toContain('Sin invitación al bot');
		manage().click();
		await tick();
		expect(page.query('.field-operator-manage-row')).toBeNull();
		// Operador inactivo: la acción se vuelve activar.
		(page.queryAll('tbody td button.button')[1] as HTMLButtonElement).click();
		await tick();
		expect(page.query('.field-operator-manage-row form[action="?/activate"]')).not.toBeNull();
	});

	it('filters rows from the search box and shows the empty state', async () => {
		const page = renderPage(baseData());
		const input = page.query('.field-search input') as HTMLInputElement;
		input.value = 'beto';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		let rows = page.queryAll('.field-operator-table-wrap tbody tr');
		expect(rows).toHaveLength(1);
		expect(page.text()).toContain('Beto López');
		input.value = 'zzz-nadie';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		expect(page.text()).toContain('Sin resultados');
		rows = page.queryAll('.field-operator-table-wrap tbody tr');
		expect(rows).toHaveLength(0);
	});

	it('keeps the alta operativa: hidden with data, open on empty, posting to ?/create', async () => {
		const withData = renderPage(baseData());
		const form = withData.query('form.field-operator-form') as HTMLFormElement;
		expect(form.hasAttribute('hidden')).toBe(true);
		expect(withData.query('button[aria-controls="operator-create-form"]')?.textContent?.trim()).toBe(
			'Alta de operador'
		);
		(withData.query('button[aria-controls="operator-create-form"]') as HTMLButtonElement).click();
		await tick();
		expect(form.hasAttribute('hidden')).toBe(false);
		expect(withData.query('form.field-operator-form input[name="display_name"]')).not.toBeNull();
		expect(withData.query('form.field-operator-form input[name="phone"]')).not.toBeNull();
		expect(withData.query('form.field-operator-form input[name="telegram_user_id"]')).not.toBeNull();

		const empty = renderPage({ operators: [] });
		const emptyForm = empty.query('form.field-operator-form') as HTMLFormElement;
		expect(emptyForm.hasAttribute('hidden')).toBe(false);
		expect((emptyForm.getAttribute('action') ?? '').includes('create')).toBe(true);
		expect(empty.text()).toContain('Sin operadores');
	});
});
