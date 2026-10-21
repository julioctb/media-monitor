// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, unmount } from 'svelte';
import { tick } from 'svelte';

import type { DailySummaryContent } from '$lib/api';
import DigestSections from './DigestSections.svelte';

function digestFixture(): DailySummaryContent {
	return {
		schema: 2,
		coverage: {
			total: 2,
			by_source: { news_rss: 2 },
			by_topic: { institutional: 1 },
			gaps: ['Facebook sin cobertura en la ventana']
		},
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

const TONES = {
	media: { positive: 3, negative: 1, neutral: 2, unclassified: 1, total: 7 },
	social: { positive: 0, negative: 0, neutral: 0, unclassified: 2, total: 2 }
};

let instance: Record<string, unknown> | undefined;

function renderCard(
	content: DailySummaryContent,
	tones: typeof TONES | null = null,
	props: Record<string, unknown> = {}
) {
	const target = document.createElement('div');
	document.body.append(target);
	instance = mount(DigestSections, { target, props: { content, tones, ...props } });
	return target;
}

function withExtraNoticia(
	third: NonNullable<DailySummaryContent['noticias']>[number]
): DailySummaryContent {
	const content = digestFixture();
	content.noticias = [...(content.noticias ?? []), third];
	return content;
}

const TONE_MAP = { 673: 'positive', 674: 'negative' };

function toneButton(host: HTMLElement, tone: string): HTMLButtonElement {
	const button = host.querySelector(`button[data-tone="${tone}"]`) as HTMLButtonElement | null;
	if (!button) throw new Error(`missing tone pill: ${tone}`);
	return button;
}

async function clickPill(host: HTMLElement, tone: string) {
	toneButton(host, tone).click();
	await tick();
}

describe('DigestSections tone pills', () => {
	afterEach(() => {
		if (instance) void unmount(instance as never);
		instance = undefined;
	});

	it('renders three tone pills mirroring the feed-filter pattern', () => {
		const host = renderCard(digestFixture(), null, { sentimentByEvent: TONE_MAP });
		for (const tone of ['positive', 'neutral', 'negative']) {
			const button = toneButton(host, tone);
			expect(button.getAttribute('aria-pressed')).toBe('false');
		}
	});

	it('filters news by tone and toggles the pill off', async () => {
		const content = withExtraNoticia({
			event_id: 674,
			title: 'Nota tono negativo',
			sources: [{ source: 'news_rss', url: 'https://n/3', title: 'N' }]
		});
		const host = renderCard(content, null, { sentimentByEvent: TONE_MAP });
		expect(host.textContent).toContain('Nota tono negativo');

		await clickPill(host, 'positive');
		expect(host.textContent).toContain('BUAP inaugura edificio en Zacapoaxtla');
		expect(host.textContent).not.toContain('Nota tono negativo');
		expect(toneButton(host, 'positive').getAttribute('aria-pressed')).toBe('true');

		await clickPill(host, 'positive');
		expect(host.textContent).toContain('Nota tono negativo');
		expect(toneButton(host, 'positive').getAttribute('aria-pressed')).toBe('false');
	});

	it('combines the tone filter with the source filter (AND)', async () => {
		const host = renderCard(digestFixture(), null, { sentimentByEvent: TONE_MAP });
		await clickPill(host, 'positive');
		const social = host.querySelector('button[data-filter="social"]') as HTMLButtonElement;
		social.click();
		await tick();
		expect(host.textContent).toContain('No hay publicaciones de redes');
		expect(host.querySelector('.news-item')).toBeNull();
	});

	it('drops items without sentiment data while a tone pill is active', async () => {
		const content = withExtraNoticia({
			event_id: null,
			title: 'Nota sin evento',
			sources: [{ source: 'news_rss', url: 'https://n/4', title: 'N' }]
		});
		const host = renderCard(content, null, { sentimentByEvent: TONE_MAP });
		expect(host.textContent).toContain('Nota sin evento');

		await clickPill(host, 'positive');
		expect(host.textContent).not.toContain('Nota sin evento');

		await clickPill(host, 'positive');
		expect(host.textContent).toContain('Nota sin evento');
	});

	it('shows the empty note instead of an empty list when no item matches', async () => {
		const host = renderCard(digestFixture(), null, { sentimentByEvent: {} });
		await clickPill(host, 'negative');
		expect(host.textContent).toContain('Ninguna nota coincide');
		expect(host.querySelector('.news-item')).toBeNull();
	});
});

describe('DigestSections', () => {
	afterEach(() => {
		if (instance) void unmount(instance as never);
		instance = undefined;
	});

	it('renders every editorial section', () => {
		const host = renderCard(digestFixture(), null, { fieldCount: 3 });
		const text = host.textContent ?? '';
		for (const heading of [
			'Resumen general',
			'Cobertura del día',
			'Datos de campo',
			'Lilia Cedillo Ramírez',
			'Feed de noticias',
			'Personas mencionadas',
			'Pendientes y silencios'
		]) {
			expect(text).toContain(heading);
		}
	});

	it('shows feed preview details and rectora watch note', () => {
		const host = renderCard(digestFixture());
		const text = host.textContent ?? '';
		expect(text).toContain('Institucional');
		expect(text).toContain('Noticias · a · b');
		expect(text).toContain('Tonos de la selección');
		expect(text).toContain('La rectora encabezó la inauguración.');
		expect(text).toContain('Por qué importa: Obra regional emblemática.');
		expect(text).toContain('Vigilar: reacciones post-votación');
		expect(text).toContain('BUAP inaugura edificio en Zacapoaxtla');
	});

	it('renders tone fallbacks and silent social sources without day stats', () => {
		const host = renderCard(digestFixture());
		const text = host.textContent ?? '';
		expect(text).toContain('Sin calcular');
		expect(text).toContain('Sin datos');
		expect(text).toContain('X: sin menciones');
		expect(text).toContain('Facebook sin cobertura en la ventana');
		expect(text).toContain('distribución no disponible');
	});

	it('renders day tone split, category bars and rectora quotes', () => {
		const host = renderCard(digestFixture(), TONES);
		const text = host.textContent ?? '';
		expect(text).toContain('Corresponde a las menciones de medios');
		expect(text).toContain('1 · 50\u00a0%');
		// Quote from the rectora news item, cited to its first source.
		expect(text).toContain('News RSS · titular de la nota');
	});

	it('falls back to action quotes when no news item matches', () => {
		const content = digestFixture();
		content.noticias = [];
		const host = renderCard(content);
		const text = host.textContent ?? '';
		expect(text).toContain('Inauguración');
		expect(text).toContain('Resumen del día');
	});

	it('hides the field data section when the day has none', () => {
		const host = renderCard({ schema: 2 });
		expect(host.textContent).toContain('Sin noticias registradas');
		expect(host.textContent).not.toContain('Aún no hay resultados de campo');
	});

	it('stamps the update as mockup copy inside <time>', () => {
		const host = renderCard(digestFixture(), null, { updatedAt: '2026-10-19T06:24:00-06:00' });
		const stamp = host.querySelector('.rectora-update time');
		expect(stamp).not.toBeNull();
		expect(stamp?.getAttribute('datetime')).toBe('2026-10-19T06:24:00-06:00');
		expect(host.textContent).toContain('Resumen actualizado el 19/10/2026 a las 06:24');
	});

	it('prefers the rectora identity stamp over the persona lookup', () => {
		const content = digestFixture();
		content.rectora = { ...content.rectora, name: 'Nombre Estampado', role: 'Cargo', org: 'Org' };
		const host = renderCard(content);
		expect(host.querySelector('#rectora-heading')?.textContent).toContain('Nombre Estampado');
		expect(host.textContent).toContain('Cargo · Org');
	});

	it('falls back to the persona chain on pre-stamp digests', () => {
		const content = digestFixture();
		const { name: _name, role: _role, org: _org, ...rectora } = content.rectora ?? {};
		content.rectora = rectora;
		const host = renderCard(content);
		expect(host.querySelector('#rectora-heading')?.textContent).toContain(
			'Lilia Cedillo Ramírez'
		);
		expect(host.textContent).toContain('Rectora · BUAP');
	});
});
