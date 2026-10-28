// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest';
import { mount, tick, unmount } from 'svelte';

import ConsultasPage from './+page.svelte';
import type { PageProps } from './$types';

const mounted: unknown[] = [];

function renderPage(form: Record<string, unknown> | null = null) {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(ConsultasPage, {
		target,
		props: {
			data: {} as PageProps['data'],
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

describe('consultas welcome suggestions', () => {
	it('renders the mockup suggestion chips inside the welcome', () => {
		const page = renderPage();
		const suggestions = page.query('.welcome .suggestions');
		expect(suggestions).not.toBeNull();
		expect(suggestions?.getAttribute('aria-label')).toBe('Preguntas sugeridas');
		const chips = page.queryAll('.suggestions button');
		expect(chips.length).toBeGreaterThanOrEqual(3);
		expect(chips.length).toBeLessThanOrEqual(4);
		for (const chip of chips) {
			expect(chip.textContent?.trim()).toMatch(/^¿.+\?$/);
			expect(chip.getAttribute('type')).toBe('button');
		}
		expect(page.text()).toContain('¿Qué se publicó esta semana sobre la BUAP?');
	});

	it('fills the composer textarea and focuses it on click', async () => {
		const page = renderPage();
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
		expect(page.text()).not.toContain('Consultando…');
	});

	it('keeps the composer intact beside the suggestions', () => {
		const page = renderPage();
		const form = page.query('form.composer');
		expect(form).not.toBeNull();
		expect(page.query('.suggestions')?.parentElement?.className).toContain('welcome');
		const textarea = page.query('textarea[name="question"]') as HTMLTextAreaElement;
		expect(textarea.getAttribute('maxlength')).toBe('1000');
		expect(page.query('button[type="submit"]')?.textContent?.trim()).toBe('Enviar pregunta');
	});
});
