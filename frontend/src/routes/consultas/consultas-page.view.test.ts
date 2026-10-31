// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, tick, unmount } from 'svelte';

import ConsultasPage from './+page.svelte';
import type { PageProps } from './$types';

const mounted: unknown[] = [];

const DIGEST_SUGGESTIONS = [
	'¿Qué se reportó sobre la mesa de movilidad?',
	'¿Qué se reportó sobre el suministro de agua?'
];

function renderPage(
	form: Record<string, unknown> | null = null,
	data: Partial<PageProps['data']> = {}
) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(ConsultasPage, {
		target,
		props: {
			data: { suggestions: [], suggestionDate: null, ...data } as PageProps['data'],
			params: {} as PageProps['params'],
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

describe('consultas mockup anatomy', () => {
	it('renders the queryView layout: chat header, welcome and history aside', () => {
		const page = renderPage();
		expect(page.query('.query-layout .panel.query-box')).not.toBeNull();
		expect(page.query('.query-chat-header h2')?.textContent).toBe('De la pregunta a la fuente');
		expect(page.query('.query-chat-header p')?.textContent).toBe('Consulta los registros del monitoreo');
		expect(page.query('.query-welcome h3')?.textContent).toBe('¿Qué quieres investigar?');
		expect(page.query('.query-welcome > p')?.textContent).toBe(
			'Explora las menciones y abre la evidencia de cada resultado.'
		);
		expect(page.query('aside.query-history h2')?.textContent).toBe('Historial de preguntas');
		expect(page.text()).toContain('El historial se guarda solo en este navegador.');
		expect(page.text()).toContain('Aún no hay preguntas guardadas.');
	});

	it('shows suggestion chips derived from the real daily digest, with its date', () => {
		const page = renderPage(null, { suggestions: DIGEST_SUGGESTIONS, suggestionDate: '25 oct' });
		const chips = page.queryAll('.query-welcome .suggestions button');
		expect(chips.map((chip) => chip.textContent?.trim())).toEqual(DIGEST_SUGGESTIONS);
		expect(page.query('.suggestions > p')?.textContent).toContain('síntesis');
		expect(page.text()).toContain('Sugerencias basadas en la síntesis del 25 oct');
	});

	it('without a daily digest there are no chips and an honest empty note', () => {
		const page = renderPage();
		expect(page.queryAll('.suggestions button').length).toBe(0);
		expect(page.text()).toContain('No hay asuntos sintetizados para esta fecha.');
	});

	it('fills the composer textarea and focuses it on click', async () => {
		const page = renderPage(null, { suggestions: DIGEST_SUGGESTIONS, suggestionDate: '25 oct' });
		await tick(); // bind:this del textarea se pobla tras el primer flush
		const chips = page.queryAll('.suggestions button') as HTMLButtonElement[];
		const question = chips[1].textContent?.trim() ?? '';
		chips[1].click();
		await tick();
		const textarea = page.query('textarea[name="question"]') as HTMLTextAreaElement;
		expect(textarea.value).toBe(question);
		// El foco vuelve al composer para editar o enviar (Enter).
		expect(document.activeElement).toBe(textarea);
		// El click no envía el formulario: el draft queda editable.
		expect(page.text()).not.toContain('Consultando');
	});

	it('keeps the mockup composer intact beside the welcome', () => {
		const page = renderPage();
		const form = page.query('form.query-composer');
		expect(form).not.toBeNull();
		const textarea = page.query('textarea[name="question"]') as HTMLTextAreaElement;
		expect(textarea.getAttribute('placeholder')).toBe('Pregunta sobre tu monitoreo...');
		expect(textarea.getAttribute('maxlength')).toBe('1000');
		expect(textarea.getAttribute('rows')).toBe('2');
		const submit = page.query('.query-composer-field button[type="submit"]');
		expect(submit?.getAttribute('aria-label')).toBe('Enviar consulta');
		expect(page.text()).toContain('Cada respuesta cita las notas que la sustentan.');
	});

	it('renders a finished turn with question, answer and per-citation evidence', async () => {
		const page = renderPage({
			question: '¿Qué se dijo del agua?',
			turn: 1,
			answer: 'Hubo dos menciones sobre el suministro.',
			citations: [
				{
					mention_id: 42,
					title: 'Vecinos reportan intermitencia',
					url: 'https://example.mx/agua',
					source: 'news',
					published_at: '2026-10-25T13:00:00Z',
					sentiment: 'neutral'
				}
			],
			error: null,
			person: null
		});
		await tick(); // el $effect persiste el turno y crea el hilo activo
		expect(page.query('.query-question p')?.textContent).toBe('¿Qué se dijo del agua?');
		expect(page.query('.answer h3')?.textContent).toBe('Respuesta');
		expect(page.query('.answer p')?.textContent).toBe('Hubo dos menciones sobre el suministro.');
		const evidence = page.query('.evidence');
		expect(evidence).not.toBeNull();
		expect(evidence?.querySelector('strong')?.textContent).toContain('[1]');
		expect(evidence?.querySelector('.text-link')?.getAttribute('href')).toBe('https://example.mx/agua');
		expect(evidence?.querySelector('.text-link')?.textContent).toContain('Abrir evidencia #42');
	});

	it('renders an inline error turn without faking an answer', async () => {
		const page = renderPage({
			question: 'corto',
			turn: 2,
			answer: null,
			citations: [],
			error: 'Escribe una pregunta de al menos 3 caracteres.',
			person: null
		});
		await tick(); // idem: el turno de error viaja por el $effect de persistencia
		expect(page.query('.query-error')?.textContent).toBe('Escribe una pregunta de al menos 3 caracteres.');
		expect(page.query('.answer')).toBeNull();
	});
});
