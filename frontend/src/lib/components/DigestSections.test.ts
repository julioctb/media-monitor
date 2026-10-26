// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, tick, unmount } from 'svelte';

import type { DailySummaryContent } from '$lib/api';
import DigestSections from './DigestSections.svelte';
import { createEvidenceContext } from '$lib/digest-evidence';

function digestFixture(): DailySummaryContent {
	return {
		schema: 2,
		coverage: {
			total: 2,
			by_source: { news_rss: 2 },
			by_topic: { institutional: 1 },
			gaps: []
		},
		noticias: [
			{
				event_id: 673,
				title: 'BUAP inaugura edificio en Zacapoaxtla',
				summary: 'La rectora encabezó la inauguración.',
				why_it_matters: 'El ajuste recorta recursos.',
				topic: 'institutional',
				confidence: 'media',
				sources: [{ source: 'news_rss', url: 'https://a/1' }]
			},
			{
				event_id: 674,
				title: 'Abrió la ofrenda de Día de Muertos',
				summary: 'La obra fue elaborada por estudiantes.',
				topic: 'culture',
				confidence: 'alta',
				sources: [
					{ source: 'rss_custom', url: 'https://b/2' },
					{ source: 'news_rss', url: 'https://c/3' }
				]
				},
			{
				event_id: 675,
				title: 'Sin tema asignado',
				summary: 'Nota sin clasificar.',
				sources: []
			}
		],
		agenda: [
			{ when: '27 oct.', status: 'Nueva, sin nota aún', title: 'Plática sobre redes de apoyo', source: 'X, @BUAPoficial' }
		],
		redes: {
			x: { count: 0 },
			facebook_page: { count: 3, note: 'Vista previa limitada por inicio de sesión.' }
		},
		personas: [{ person_id: 88, name: 'Lilia Cedillo Ramírez', mention_count: 2 }],
		pendientes: ['Sin notas nuevas fechables en e-consulta.']
	};
}

const TONES = {
	media: { positive: 3, negative: 1, neutral: 2, unclassified: 1, total: 7 },
	social: { positive: 0, negative: 0, neutral: 0, unclassified: 2, total: 2 },
	field: { positive: 0, negative: 1, neutral: 0, unclassified: 0, total: 1 }
};

let instance: Record<string, unknown> | undefined;

function renderSection(
	content: DailySummaryContent,
	tones: typeof TONES | null = null,
	props: Record<string, unknown> = {}
) {
	const target = document.createElement('div');
	document.body.append(target);
	instance = mount(DigestSections, { target, props: { content, tones, ...props } });
	return target;
}

describe('DigestSections v2', () => {
	afterEach(() => {
		if (instance) void unmount(instance as never);
		instance = undefined;
	});

	it('renders the three summary boxes and the detail header', () => {
		const host = renderSection(digestFixture(), TONES, { sourcesCount: 12 });
		const text = (host.textContent ?? '').replace(/\s+/g, ' ');
		for (const heading of ['Noticias', 'Redes Sociales', 'Datos de Campo', 'Resumen detallado del día']) {
			expect(text).toContain(heading);
		}
		expect(text).toContain('12 fuentes activas');
		expect(text).toContain('7 notas registradas');
		expect(text).toContain('2 publicaciones registradas');
		expect(text).toContain('1 registro cargado');
	});

	it('falls back to the mockup empty states without day stats', () => {
		const host = renderSection(digestFixture(), null, {});
		const text = host.textContent ?? '';
		expect(text).toContain('Sin calcular');
		expect(text).toContain('Sin datos');
		expect(text).toContain('fuentes activas');
		// The window claims only render with real buckets.
		expect(text).not.toContain('Corresponde a las menciones de medios');
	});

	it('groups noticias under topic headings with source and confidence', () => {
		const host = renderSection(digestFixture());
		const blocks = [...host.querySelectorAll('.daily-detail-block')];
		const news = blocks.find((block) => block.querySelector('h3')?.textContent === 'Noticias');
		expect(news).toBeDefined();
		const topics = [...news!.querySelectorAll('h4')].map((h) => h.textContent);
		expect(topics).toEqual(['Institucional', 'Cultura', 'Sin categoría']);
		expect(news!.textContent).toContain('Fuente: News RSS. Confianza: media.');
		expect(news!.textContent).toContain('Fuente: RSS propios · News RSS. Confianza: alta.');
	});

	it('shows the review, never the headline, and flags negatives with reason', () => {
		const host = renderSection(digestFixture(), null, {
			negativeEvents: [{ event_id: 673, title: 'x', source: 'news_rss', published_at: null }]
		});
		const entries = [...host.querySelectorAll('.daily-detail-entry')];
		const negative = entries.find((entry) => entry.textContent.includes('encabezó'));
		const plain = entries.find((entry) => entry.textContent.includes('obra fue elaborada'));
		// The review is the body; the headline never renders (it lives in the feed).
		expect(negative!.textContent).toContain('La rectora encabezó la inauguración.');
		expect(negative!.textContent).not.toContain('Zacapoaxtla');
		// Negative entries carry the call with its reason when the digest has one.
		expect(negative!.querySelector('.daily-detail-negative')?.textContent).toContain(
			'Nota negativa'
		);
		expect(negative!.querySelector('.daily-detail-negative')?.textContent).toContain(
			'El ajuste recorta recursos.'
		);
		expect(plain!.querySelector('.daily-detail-negative')).toBeNull();
	});

	it('stamps the local date, recovered tag and justified confidence', () => {
		const content = digestFixture();
		content.noticias![0].when_label = '22 oct.';
		content.noticias![0].repeat = true;
		content.noticias![0].confidence_note = 'fuente oficial directa';
		const host = renderSection(content);
		const entry = [...host.querySelectorAll('.daily-detail-entry')][0];
		expect(entry!.textContent).toContain('22 oct. · Nota recuperada — ');
		expect(entry!.querySelector('.daily-detail-source')?.textContent).toContain(
			'Confianza: media — fuente oficial directa'
		);
	});

	it('lists silent themes under noticias and accounts under redes', () => {
		const content = digestFixture();
		content.temas_sin_nota = ['Pensiones / Relaciones laborales'];
		(content.redes ?? {}).x = {
			count: 2,
			note: 'Actividad cubierta por notas del día.',
			cuentas: [{ cuenta: '@BUAPoficial', nota: 'solo recapitulaciones' }]
		};
		const host = renderSection(content);
		const tema = host.querySelector('.daily-detail-tema');
		expect(tema?.querySelector('h4')?.textContent).toBe('Pensiones / Relaciones laborales');
		expect(tema?.textContent).toContain('Sin novedades identificadas');
		const cuenta = host.querySelector('.daily-detail-cuenta');
		expect(cuenta?.textContent).toContain('@BUAPoficial — solo recapitulaciones');
	});

	it('renders agenda and limitations', () => {
		const host = renderSection(digestFixture());
		const text = host.textContent ?? '';
		expect(text).toContain('27 oct. · Nueva, sin nota aún');
		expect(text).toContain('Plática sobre redes de apoyo');
		expect(text).toContain('Fuente: X, @BUAPoficial');
		expect(text).toContain('Limitaciones de cobertura');
		expect(text).toContain('Sin notas nuevas fechables en e-consulta.');
	});

	it('marks silent tracked sources with the fixed line and honors label overrides', () => {
		const host = renderSection(digestFixture(), null, {
			socialLabels: { facebook_page: 'Facebook · BUAPoficial' }
		});
		const text = host.textContent ?? '';
		expect(text).toContain('Sin novedades fechables en la ventana.');
		const social = [...host.querySelectorAll('.daily-detail-block')].find((block) =>
			block.textContent?.includes('Redes sociales')
		);
		expect(social?.textContent).toContain('Facebook · BUAPoficial');
		expect(social?.textContent).toContain('Vista previa limitada por inicio de sesión.');
	});

	it('omits the detail section when the content has nothing', () => {
		const host = renderSection({ schema: 2 });
		expect((host.textContent ?? '')).not.toContain('Resumen detallado del día');
	});

	it('tolerates legacy rows that still carry a rectora key (section removed)', () => {
		const content = {
			...digestFixture(),
			rectora: {
				person_id: 88,
				name: 'Lilia Cedillo Ramírez',
				activity: [{ when: '22 oct.', text: 'Inauguró la ofrenda en la Casa de la Bóveda.', channel: 'X' }]
			}
		} as unknown as DailySummaryContent;
		const host = renderSection(content);
		// Old row shape: the stored key rides along, the section never renders.
		expect(host.textContent).not.toContain('Rectora Lilia Cedillo Ramírez');
		expect(host.textContent).not.toContain('Casa de la Bóveda');
		expect(host.textContent).toContain('Limitaciones de cobertura');
	});
});

it('adds raw field receipts to existing news, confidence, negative, agenda and network prose', async () => {
  const content = digestFixture();
  content.evidence = { version: 1, sources: [
    { index: 0, mention_id: 1, source: 'news_rss', url: 'https://medio.example/0', outlet: 'medio.example', author: null, title: 'Medio', published_at: null, summary: null, excerpt: 'Material' },
    { index: 1, mention_id: 2, source: 'x_twitter', url: 'https://x.com/cuenta/status/2', outlet: 'x.com', author: '@cuenta', title: 'Publicación X', published_at: null, summary: null, excerpt: 'Material X' }
  ] };
  const fingerprint = (await createEvidenceContext(content))!.fingerprint;
  function bind(target: Record<string, unknown>, field: string, ref: number) {
    target.provenance = { ...(target.provenance as object ?? {}), [field]: { text: target[field], source_refs: [ref], state: 'linked', origin: 'model_output', catalogue_fingerprint: fingerprint } };
  }
  const noticia = content.noticias![0];
  noticia.source_refs = [0];
  noticia.summary = ' Reseña https://enlace.example/ íntegra ';
  noticia.confidence_note = 'Nota de confianza';
  for (const field of ['summary', 'why_it_matters', 'confidence_note']) bind(noticia as unknown as Record<string, unknown>, field, 0);
  const agenda = content.agenda![0];
  for (const field of ['when', 'status', 'title', 'source']) bind(agenda as unknown as Record<string, unknown>, field, 0);
  const account = { cuenta: '@cuenta', nota: 'Lectura de cuenta' };
  const network = { count: 1, note: 'Lectura de red', cuentas: [account] };
  bind(network, 'note', 1); bind(account, 'cuenta', 1); bind(account, 'nota', 1);
  content.redes = { x: network };
  const host = renderSection(content, null, { negativeEvents: [{ event_id: 673 }] });
  await new Promise(resolve => setTimeout(resolve, 30)); await tick();
  const first = host.querySelector('.daily-detail-entry')!;
  expect(first.querySelectorAll('details')).toHaveLength(3);
  expect(first.textContent).toContain('Reseña íntegra');
  const agendaBlock = [...host.querySelectorAll('.daily-detail-block')].find(block => block.querySelector('h3')?.textContent === 'Agenda')!;
  expect(agendaBlock.querySelectorAll('details')).toHaveLength(4);
  const social = [...host.querySelectorAll('.daily-detail-block')].find(block => block.querySelector('h3')?.textContent === 'Redes sociales')!;
  expect(social.querySelectorAll('details')).toHaveLength(3);
  expect([...social.querySelectorAll('a')].map(link => link.getAttribute('href'))).toEqual(Array(3).fill('https://x.com/cuenta/status/2'));
});
