// @vitest-environment jsdom
import { mount, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { DailySummaryContent } from '$lib/api';

import DigestV3 from './DigestV3.svelte';

/**
 * Container behavior: v3 rows render brief + evidencia + campo; legacy v2
 * rows render NOTHING (the home keeps its layout, no ghost sections).
 */

const mounted: Array<Record<string, unknown>> = [];

function render(content: unknown): { text: () => string; html: () => string } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(DigestV3, {
		target,
		props: { content: content as never }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	return {
		text: () => (target.textContent ?? '').replace(/\s+/g, ' '),
		html: () => target.innerHTML
	};
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

function v3Content(): Record<string, unknown> {
	return {
		schema: 2,
		noticias: [],
		brief: {
			headline: 'Titular del día',
			delta: ['Nueva historia: A'],
			decisiones: [{ index: 0, categoria: 'decision', razon: 'Impacto presupuestal' }],
			ruido: [],
			a_favor: [],
			fechas: [{ title: 'Cierre', when: '27 oct.', estado: 'proxima', fecha: '2026-10-27' }]
		},
		tarjetas: [
			{
				titulo: 'A',
				hecho: 'Hecho uno',
				por_que: 'Porque importa',
				fuentes: ['news_rss'],
				tono: 'negativo',
				repeat: true
			},
			{ titulo: 'B', hecho: 'Hecho dos', fuentes: [], repeat: false }
		],
		campo: [
			{ titulo: 'Reporte', contenido: 'Texto', estado: 'publicada' },
			{ titulo: 'Pendiente', estado: 'en revisión' }
		]
	};
}

it('renders nothing for legacy v2 content', () => {
	const view = render({ schema: 2, noticias: [], plain_text: 'x' });
	expect(view.text()).toBe('');
});

it('renders brief, evidencia and campo for a v3 row', () => {
	const { text } = render(v3Content());
	const copy = text();

	// Brief hero.
	expect(copy).toContain('Brief del día');
	expect(copy).toContain('Titular del día');
	expect(copy).toContain('Qué cambió');
	expect(copy).toContain('Nueva historia: A');
	expect(copy).toContain('Decisión / atención');
	expect(copy).toContain('A — Impacto presupuestal');
	expect(copy).toContain('Fechas que obligan');
	expect(copy).toContain('Próxima Cierre (27 oct.)');

	// Evidencia cards: hecho, por qué, fuente y badges.
	expect(copy).toContain('Evidencia del día');
	expect(copy).toContain('Hecho uno');
	expect(copy).toContain('Por qué — Porque importa');
	expect(copy).toContain('Fuente: News RSS');
	expect(copy).toContain('Reiteración');
	expect(copy).toContain('negativo');

	// Campo with the workflow estado visible.
	expect(copy).toContain('Campo');
	expect(copy).toContain('publicada');
	expect(copy).toContain('en revisión');
});

it('hides absent pieces: no por_que, no ghost sections', () => {
	const content = v3Content();
	const tarjetas = content.tarjetas as Record<string, unknown>[];
	tarjetas[1].hecho = null;
	delete tarjetas[0].por_que;
	delete content.campo;
	const { text } = render(content);

	expect(text()).not.toContain('Por qué');
	expect(text()).not.toContain('Hecho dos');
	// Campo section gated on real data.
	expect(text()).not.toContain('reportes en la ventana');
	expect(text()).toContain('Hecho uno');
});
