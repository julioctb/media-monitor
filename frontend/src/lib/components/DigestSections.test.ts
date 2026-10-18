// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';

import type { DailySummaryContent } from '$lib/api';
import DigestSections from './DigestSections.svelte';

function digestFixture(): DailySummaryContent {
	return {
		schema: 2,
		coverage: { total: 2, by_source: { news_rss: 2 }, gaps: ['Facebook sin cobertura en la ventana'] },
		noticias: [
			{
				event_id: 673,
				title: 'BUAP inaugura edificio en Zacapoaxtla',
				summary: 'La rectora encabezó la inauguración.',
				why_it_matters: 'Obra regional emblemática.',
				topic: 'institutional',
				confidence: 'media',
				sources: [
					{ source: 'news_rss', url: 'https://a/1', title: 'A' },
					{ source: 'rss_custom', url: 'https://b/2', title: 'B' }
				],
				person_ids: [88]
			}
		],
		rectora: {
			person_id: 88,
			mention_count: 1,
			actions: [{ title: 'Inauguración', event_id: 673, sentiment: 'positive' }],
			tone: 'positivo',
			watch: 'reacciones post-votación'
		},
		redes: {
			x: { count: 0 },
			facebook_page: { count: 1 }
		},
		personas: [
			{
				person_id: 88,
				name: 'Lilia Cedillo Ramírez',
				role: 'Rectora',
				org: 'BUAP',
				mention_count: 1,
				fact: 'BUAP inaugura edificio en Zacapoaxtla'
			}
		],
		pendientes: ['«sin datos» sin menciones']
	};
}

let instance: Record<string, unknown> | undefined;

function renderCard(content: DailySummaryContent) {
	const target = document.createElement('div');
	document.body.append(target);
	instance = mount(DigestSections, { target, props: { content } });
	return target;
}

describe('DigestSections', () => {
	afterEach(() => {
		if (instance) void unmount(instance as never);
		instance = undefined;
	});

	it('renders every editorial section', () => {
		const host = renderCard(digestFixture());
		const text = host.textContent ?? '';
		for (const heading of ['Noticias', 'Rectora', 'Redes sociales', 'Personas mencionadas', 'Pendientes']) {
			expect(text).toContain(heading);
		}
	});

	it('shows topic, confidence, sources and rectora tone', () => {
		const host = renderCard(digestFixture());
		const text = host.textContent ?? '';
		expect(text).toContain('Institucional');
		expect(text).toContain('Confianza media');
		expect(text).toContain('La rectora encabezó la inauguración.');
		expect(text).toContain('Por qué importa: Obra regional emblemática.');
		expect(text).toContain('Tono: positivo');
		expect(text).toContain('reacciones post-votación');
		expect(text).toContain('BUAP inaugura edificio en Zacapoaxtla');
	});

	it('marks silent social sources and lists gaps', () => {
		const host = renderCard(digestFixture());
		const text = host.textContent ?? '';
		expect(text).toContain('sin menciones');
		expect(text).toContain('Facebook sin cobertura en la ventana');
	});

	it('renders empty state without crash', () => {
		const host = renderCard({ schema: 2 });
		expect(host.textContent).toContain('Sin noticias registradas');
	});
});
