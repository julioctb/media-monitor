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
				operator_id: 99,
				published_at: '2026-10-27T18:00:00+00:00'
			}),
			report({
				id: 3,
				status: 'rejected',
				title: 'Ruido en la feria',
				content: 'Queja por amplificadores después de medianoche.',
				review_note: 'Fuera de cobertura'
			})
		],
		operators: [
			{
				id: 7,
				display_name: 'Ana Torres',
				telegram_user_id: 111222,
				phone: '+52 22 21 23 45 67',
				active: true,
				invited_at: null,
				accepted_at: null,
				last_report_at: '2026-10-27T15:30:00+00:00'
			},
			{
				id: 8,
				display_name: 'Beto Ruiz',
				telegram_user_id: null,
				phone: '+52 22 99 88 77 66',
				active: false,
				invited_at: null,
				accepted_at: null,
				last_report_at: null
			}
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
		click: async (selector: string, index = 0) => {
			const el = target.querySelectorAll(selector)[index] as HTMLButtonElement | undefined;
			el?.click();
			await tick();
		},
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

async function toReports(page: ReturnType<typeof renderPage>) {
	await page.click('.field-top .tab[aria-pressed="false"]');
}

describe('campo: una sola página con las dos pestañas del mockup', () => {
	it('abre en «Listado de operadores» con toolbar, columnas y shell de paginación', () => {
		const page = renderPage(baseData());
		const text = page.text();
		expect(text).toContain('Campo');
		expect(text).toContain('Operadores y reportes de territorio.');
		expect(text).toContain('Listado de operadores');
		expect(text).toContain('Reportes de operadores');
		expect(text).toContain('2 operadores registrados');
		expect(text).toContain('Nombre');
		expect(text).toContain('ID de Telegram');
		expect(text).toContain('Último reporte');
		expect(text).toContain('Ana Torres');
		expect(text).toContain('1–2 de 2 · Página 1 de 1');
		// la pestaña activa es la de operadores (mockup abre ahí)
		expect(page.query('.field-top .tab.active')?.textContent?.trim()).toBe('Listado de operadores');
	});

	it('la pestaña reportes muestra la bandeja con conteos y estados reales', async () => {
		const page = renderPage(baseData());
		await toReports(page);
		const text = page.text();
		expect(text).toContain('Bandeja de reportes');
		expect(text).toContain('3 reportes registrados');
		expect(text).toContain('Por revisar1');
		expect(text).toContain('Publicado1');
		expect(text).toContain('Descartado1');
		expect(page.query('table.field-inbox-table')).not.toBeNull();
		expect(page.query('.field-inbox-state.review')?.textContent?.trim()).toBe('Por revisar');
	});

	it('resuelve el operador por nombre real y hace fallback sin inventar', async () => {
		const page = renderPage(baseData());
		await toReports(page);
		// reporte 1 -> operador 7 conocido
		expect(page.text()).toContain('Ana Torres');
		const tabs = page.queryAll('.field-inbox-status button');
		(tabs[1] as HTMLButtonElement).click();
		await tick();
		// reporte 2 -> operador_id 99, fuera del listado: fallback estable
		expect(page.text()).toContain('Operador #99');
	});

	it('filtra por pestaña de estado', async () => {
		const page = renderPage(baseData());
		await toReports(page);
		const tabs = page.queryAll('.field-inbox-status button');
		expect(tabs).toHaveLength(3);
		(tabs[1] as HTMLButtonElement).click();
		await tick();
		const text = page.text();
		expect(text).toContain('Pavimentación terminada');
		expect(text).not.toContain('Bloqueo en la entrada norte');
		expect(page.query('.field-inbox-state.published')).not.toBeNull();
	});

	it('la búsqueda de reportes coincide por título, operador o lugar y muestra el vacío del mockup', async () => {
		const page = renderPage(baseData());
		await toReports(page);
		const input = page.query('.reports-view .field-search input') as HTMLInputElement;
		input.value = 'ana';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		expect(page.text()).toContain('Bloqueo en la entrada norte');
		input.value = 'imposible de encontrar';
		input.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		expect(page.text()).toContain('Sin resultados');
		expect(page.text()).toContain('No hay registros en esta selección. Prueba otro filtro o búsqueda.');
		// el shell de resultados (paginación) sigue visible con 0
		expect(page.text()).toContain('0–0 de 0 · Página 1 de 1');
	});

	it('abre el modal de reporte pendiente con titular/sentimiento IA, resumen y motivo', async () => {
		const page = renderPage(baseData());
		await toReports(page);
		await page.click('table .button');
		expect(page.query('dialog')).not.toBeNull();
		const text = page.text();
		expect(text).toContain('REPORTE #1 · Por revisar');
		expect(text).toContain('Reporte original');
		expect(page.query('dialog input[name="title"]')).not.toBeNull();
		const tone = page.query('dialog input[disabled]');
		expect(tone).not.toBeNull();
		expect(page.query('dialog textarea[name="content"]')).not.toBeNull();
		expect(page.query('dialog textarea[name="note"]')).not.toBeNull();
		expect(page.query('button[formaction="?/approve"]')?.textContent?.trim()).toBe('Publicar en el Feed');
		expect(page.query('button[formaction="?/reject"]')?.textContent?.trim()).toBe('Descartar');
	});

	it('muestra «Ver en el Feed» en reportes publicados', async () => {
		const page = renderPage(baseData());
		await toReports(page);
		await page.click('.field-inbox-status button', 1);
		await page.click('table .button');
		const link = page.query('.field-report-dialog a[href="/feed?source=field_report"]');
		expect(link?.textContent?.trim()).toBe('Ver en el Feed');
	});

	it('el alta abre el modal con Nombre/Teléfono y Telegram pendiente de vinculación', async () => {
		const page = renderPage(baseData());
		await page.click('.field-operator-tools .button.primary');
		const dialog = page.query('dialog');
		expect(dialog).not.toBeNull();
		const text = page.text();
		expect(text).toContain('Alta de operador');
		expect(text).toContain('Pendiente de vinculación');
		expect(text).toContain('Se asignará mediante el bot');
		expect(page.query('dialog input[name="display_name"]')).not.toBeNull();
		expect(page.query('dialog input[name="phone"]')).not.toBeNull();
		expect(page.query('dialog input[name="id"]')).toBeNull();
		expect(page.query('dialog button[type="submit"][formaction]')).toBeNull();
	});

	it('gestionar abre la ficha con ID de Telegram solo lectura y acciones reales', async () => {
		const page = renderPage(baseData());
		await page.click('.field-table .button');
		const text = page.text();
		expect(text).toContain('Gestionar operador');
		expect(text).toContain('111222');
		expect(text).toContain('Asignado por el bot · solo lectura');
		expect(text).toContain('Guardar cambios');
		expect(text).toContain('Desactivar');
		expect(text).toContain('Invitar al bot');
		expect((page.query('dialog input[name="id"]') as HTMLInputElement | null)?.value).toBe('7');
		expect((page.query('dialog input[name="display_name"]') as HTMLInputElement | null)?.value).toBe(
			'Ana Torres'
		);
	});

	it('el vacío de operadores usa el texto del mockup con shell visible', async () => {
		const page = renderPage({ ...baseData(), operators: [] });
		const text = page.text();
		expect(text).toContain('0 operadores registrados');
		expect(text).toContain('No hay registros en esta selección. Prueba otro filtro o búsqueda.');
		expect(text).toContain('0–0 de 0 · Página 1 de 1');
	});

	it('cambiar de pestaña reinicia la búsqueda (mockup resetea fieldUI)', async () => {
		const page = renderPage(baseData());
		const opsInput = page.query('.operators-view .field-search input') as HTMLInputElement;
		opsInput.value = 'ana';
		opsInput.dispatchEvent(new Event('input', { bubbles: true }));
		await tick();
		await toReports(page);
		await page.click('.field-top .tab[aria-pressed="false"]');
		const back = page.query('.operators-view .field-search input') as HTMLInputElement;
		expect(back.value).toBe('');
		expect(page.text()).toContain('1–2 de 2 · Página 1 de 1');
	});
});
