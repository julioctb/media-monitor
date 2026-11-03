// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, expect, it, vi } from 'vitest';
import { fromStore, writable } from 'svelte/store';
import type { PageProps, SubmitFunction } from '../routes/settings/$types';

const enhanced = vi.hoisted(() => new Map<HTMLFormElement, SubmitFunction>());
vi.mock('$app/forms', () => ({
	enhance: (form: HTMLFormElement, submit: SubmitFunction) => {
		enhanced.set(form, submit);
		return { destroy: () => enhanced.delete(form) };
	}
}));

import type { ClientSettings, Keyword, PersonSummary } from '$lib/api';

import SettingsPage from '../routes/settings/+page.svelte';

/**
 * Settings page view: the X section's mode switch drives the free-mode
 * limitations banner and the masked-key status line. The banner must
 * react to the radio WITHOUT a save (mirror of the mockup's provider
 * panel, which toggles on selection). The fuentes tab renders ONE
 * directory at a time behind the two-level sub-nav (mockup settings.js).
 */

const SETTINGS_VIEW: ClientSettings = {
	id: 1,
	client_id: 1,
	client_name: 'acme',
	timezone: 'America/Mexico_City',
	retention_days: 30,
	digest_hours: [21],
	digest_focus_person_id: null,
	watchlist: [2, 5],
	enrich_max_per_cycle: 40,
	fetch_max_per_cycle: 120,
	gdelt_enabled: true,
	facebook_pages: [],
	rss_feeds: [],
	scrapers: [],
	ai_provider: 'local',
	ai_api_key: null,
	ai_base_url: null,
	ai_model: null,
	ai_model_fast: null,
	x_mode: 'free',
	x_api_key: '',
	x_api_key_set: false,
	updated_at: '2026-10-22T03:00:00Z'
};

function pageSettings(overrides: Partial<ClientSettings> = {}): ClientSettings {
	return { ...SETTINGS_VIEW, ...overrides };
}

const mounted: Array<Record<string, unknown>> = [];

function renderPage(
	settings: ClientSettings,
	persons: PersonSummary[] = [],
	keywords: Keyword[] = []
): { text: () => string; target: HTMLDivElement; refresh: (settings: ClientSettings, form?: PageProps['form']) => void } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const dataStore = writable<PageProps['data']>({
		settings: { ...settings, digest_reviewer_api_key: settings.digest_reviewer_api_key ?? '' },
		scrapersAvailable: [], keywords, persons
	});
	const formStore = writable<PageProps['form']>(null);
	const pageData = fromStore(dataStore);
	const pageForm = fromStore(formStore);
	const instance = mount(SettingsPage, {
		target,
		props: { params: {}, get data() { return pageData.current; }, get form() { return pageForm.current; } }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	// Flush initial bindings/effects before inspecting or interacting with controls.
	flushSync();
	// Markup wraps lines: collapse whitespace so copy asserts survive reflows.
	return { text: () => (target.textContent ?? '').replace(/\s+/g, ' '), target,
		refresh: (settings, form = null) => flushSync(() => {
			dataStore.set({ settings: { ...settings, digest_reviewer_api_key: settings.digest_reviewer_api_key ?? '' },
				scrapersAvailable: [], keywords, persons });
			formStore.set(form);
		}) };
}

/** Click a workspace/sub-nav button by its exact label. */
function clickLabeled(
	scope: ParentNode,
	selector: string,
	label: string
): HTMLButtonElement {
	const button = [...scope.querySelectorAll(selector)].find(
		(element) => (element.textContent ?? '').trim() === label
	);
	expect(button, `button ${label} within ${selector}`).toBeInstanceOf(HTMLButtonElement);
	flushSync(() => (button as HTMLButtonElement).click());
	return button as HTMLButtonElement;
}

/** Opens the Fuentes tab; an optional sub-nav label selects the sub-tab. */
function openFuentes(target: HTMLDivElement, subNav?: string): void {
	clickLabeled(target, '.config-tabs button', 'Fuentes');
	if (subNav) clickLabeled(target, '.config-source-nav button', subNav);
}

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
	// Tab clicks deep-link via replaceState; jsdom shares one URL across
	// tests, so the next mount would otherwise open on #fuentes.
	window.history.replaceState(null, '', window.location.pathname);
});

const BANNER_HEAD = 'Modo gratuito: las menciones de X provienen del índice de Google News';
const FALLBACK_NOTE = 'Sin key: se usará el modo gratuito como respaldo';

it('shows the free limitations banner and hides the paid-only key field', () => {
	const { target, text } = renderPage(pageSettings({ x_mode: 'free', x_api_key_set: true }));
	openFuentes(target, 'Redes sociales');
	clickLabeled(target, '.config-source-nav button', 'Twitter / X');

	expect(text()).toContain(BANNER_HEAD);
	expect(text()).toContain('sin autor de la cuenta');
	expect(text()).toContain('cobertura parcial');
	expect(text()).toContain('la publicación puede tardar horas en reflejarse');
	// The API key field is paid-only: absent (input AND stored note) under free.
	expect(document.querySelector('input#x-api-key')).toBeNull();
	expect(text()).not.toContain('API key guardada');
	expect(text()).not.toContain(FALLBACK_NOTE);
});

it('hides the banner on paid and warns about the free fallback', () => {
	const { target, text } = renderPage(pageSettings({ x_mode: 'paid', x_api_key_set: false }));
	openFuentes(target, 'Redes sociales');
	clickLabeled(target, '.config-source-nav button', 'Twitter / X');

	expect(text()).not.toContain(BANNER_HEAD);
	expect(text()).not.toContain('API key guardada');
	expect(text()).toContain(FALLBACK_NOTE);
	// Paid mode reveals the key field.
	expect(document.querySelector('input#x-api-key')).toBeInstanceOf(HTMLInputElement);
});

it('reveals the banner as soon as free is selected, without saving', () => {
	const { target, text } = renderPage(pageSettings({ x_mode: 'paid', x_api_key_set: false }));
	openFuentes(target, 'Redes sociales');
	clickLabeled(target, '.config-source-nav button', 'Twitter / X');
	const radio = target.querySelector('input[name="x_mode"][value="free"]');
	expect(radio).toBeInstanceOf(HTMLInputElement);

	const free = radio as HTMLInputElement;
	free.checked = true;
	free.dispatchEvent(new Event('change', { bubbles: true }));
	flushSync();

	expect(text()).toContain(BANNER_HEAD);
	expect(text()).not.toContain(FALLBACK_NOTE); // the fallback note is paid-conditional
	expect(document.querySelector('input#x-api-key')).toBeNull(); // so is the field
});

it('reveals the API key field only under paid, without saving', () => {
	const { target, text } = renderPage(pageSettings({ x_mode: 'free', x_api_key_set: true }));
	openFuentes(target, 'Redes sociales');
	clickLabeled(target, '.config-source-nav button', 'Twitter / X');
	expect(document.querySelector('input#x-api-key')).toBeNull();

	const paid = target.querySelector('input[name="x_mode"][value="paid"]') as HTMLInputElement;
	paid.checked = true;
	paid.dispatchEvent(new Event('change', { bubbles: true }));
	flushSync();

	expect(document.querySelector('input#x-api-key')).toBeInstanceOf(HTMLInputElement);
	expect(text()).toContain('API key guardada');
	expect(text()).not.toContain(BANNER_HEAD);
});


it('renders the v3 schedule selects and preserves hidden settings', () => {
	const { text } = renderPage(
		pageSettings({ digest_hours: [8, 21], gdelt_enabled: true, enrich_max_per_cycle: 40 })
	);

	expect(text()).toContain('Horarios del resumen diario');
	const selects = [
		...document.querySelectorAll('select[name="digest_hour"]')
	] as HTMLSelectElement[];
	expect(selects.map((select) => select.value)).toEqual(['8', '21']);
	expect(text()).toContain('Todos los días · Hora de Ciudad de México · Entre 1 y 8 horarios.');

	// Preserved fields travel hidden on every save.
	const hidden = (name: string) =>
		document.querySelector(`input[name="${name}"]`) as HTMLInputElement | null;
	expect(hidden('timezone')?.value).toBe('America/Mexico_City');
	expect(hidden('enrich_max_per_cycle')?.value).toBe('40');
	expect(hidden('gdelt_enabled')?.value).toBe('1');
	expect(hidden('facebook_pages')).toBeInstanceOf(HTMLInputElement);
});

it('renders facebook directory rows with the single-span pagination', () => {
	const { target } = renderPage(
		pageSettings({
			facebook_pages: [
				{ page_id: '61593006365773', label: 'Buapachosos' },
				{ page_id: '10006932572555', label: '' }
			]
		})
	);
	openFuentes(target, 'Redes sociales'); // social defaults to the Facebook directory

	const table = target.querySelector('table[aria-label="Páginas de Facebook del monitoreo"]');
	expect(table).toBeInstanceOf(HTMLTableElement);
	const rows = [...(table as HTMLTableElement).querySelectorAll('tbody tr')];
	expect(rows.length).toBe(2);
	expect(rows[0].textContent).toContain('Buapachosos');
	expect(rows[1].textContent).toContain('Sin etiqueta');

	// One page only: single status span, Anterior/Siguiente stay unrendered.
	const pagination = target.querySelector('.config-pagination');
	expect(pagination?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
		'1–2 de 2 · Página 1 de 1'
	);
	expect(pagination?.querySelector('button')).toBeNull();

	// The serialized payload carries normalized refs for the save action.
	const payload = JSON.parse(
		(document.querySelector('input[name="facebook_pages"]') as HTMLInputElement).value
	) as { page_id: string }[];
	expect(payload.map((page) => page.page_id)).toEqual(['61593006365773', '10006932572555']);
});

it('pages the facebook directory every 10 rows with visible prev/next', () => {
	const pages = Array.from({ length: 11 }, (_, index) => ({
		page_id: `id-${index}`,
		label: `Página ${index}`
	}));
	const { target } = renderPage(pageSettings({ facebook_pages: pages }));
	openFuentes(target, 'Redes sociales');

	const pagination = target.querySelector('.config-pagination');
	expect(pagination?.textContent?.replace(/\s+/g, ' ').trim()).toContain(
		'1–10 de 11 · Página 1 de 2'
	);
	const next = [...(pagination?.querySelectorAll('button') ?? [])].find(
		(button) => button.textContent?.trim() === 'Siguiente'
	) as HTMLButtonElement;
	expect(next).toBeInstanceOf(HTMLButtonElement);
	flushSync(() => next.click());
	expect(target.querySelector('.config-pagination')?.textContent).toContain('Página 2 de 2');
	const rows = target.querySelectorAll('#fuentes tbody tr');
	expect(rows.length).toBe(1);
});

it('renders the rss directory, its live search and the planned social tiles', () => {
	const { target, text } = renderPage(pageSettings({ rss_feeds: ['https://ejemplo.com/feed.xml'] }));

	// Default sub-tab: the RSS directory with derived names and search box.
	openFuentes(target);
	const table = target.querySelector('table[aria-label="Fuentes RSS del monitoreo"]');
	expect(table).toBeInstanceOf(HTMLTableElement);
	expect(table?.querySelector('tbody tr')?.textContent).toContain('ejemplo.com');
	expect(table?.querySelector('tbody tr')?.textContent).toContain(
		'https://ejemplo.com/feed.xml'
	);
	expect(table?.querySelector('.config-rss-empty')).toBeNull();

	// The search box filters on input; the empty state names the query.
	const search = target.querySelector<HTMLInputElement>('#fuentes .config-rss-search-box input');
	expect(search).toBeInstanceOf(HTMLInputElement);
	search!.value = 'noexiste';
	search!.dispatchEvent(new Event('input', { bubbles: true }));
	flushSync();
	expect(target.querySelector('#fuentes .config-rss-empty')?.textContent).toContain(
		'No hay fuentes que coincidan con la búsqueda.'
	);

	// Social sub-nav: planned platforms render one tile at a time.
	openFuentes(target, 'Redes sociales');
	clickLabeled(target, '.config-source-nav button', 'TikTok');
	expect(text()).toContain('TikTok');
	expect(text()).toContain('La integración con TikTok aún no está disponible');
	expect(target.querySelector('.config-chip')?.textContent?.trim()).toBe('En desarrollo');
	clickLabeled(target, '.config-source-nav button', 'Instagram');
	expect(text()).toContain('La integración con Instagram aún no está disponible');
});

const FOCUS_PERSON: PersonSummary = {
	id: 7,
	name: 'Person A',
	name_key: 'person a',
	role: 'Rectora',
	org: 'BUAP',
	aliases: ['Alias A'],
	first_seen_at: '2026-10-25T12:00:00Z',
	last_seen_at: '2026-10-25T12:00:00Z',
	mention_count: 1
};

it('renders the persisted principal as one successful form control', () => {
	const { target } = renderPage(pageSettings({ digest_focus_person_id: 7 }), [FOCUS_PERSON]);
	const select = target.querySelector<HTMLSelectElement>('#set-focus-person');
	expect(select).not.toBeNull();
	expect(select!.value).toBe('7');
	expect(select!.labels?.[0]?.textContent).toContain('Persona principal bajo seguimiento');
	expect(select!.closest('#operacion .config-form-grid')).not.toBeNull();
	expect(select!.selectedOptions[0].textContent).toContain('Person A · Rectora · BUAP');
	expect(select!.form?.getAttribute('action')).toBe('?/save');
	expect(new FormData(select!.form!).getAll('digest_focus_person_id')).toEqual(['7']);
});

it('changes and clears the principal without altering the watchlist', () => {
	const other = { ...FOCUS_PERSON, id: 8, name: 'Person B', name_key: 'person b' };
	const watched = [
		{ ...FOCUS_PERSON, id: 2, name: 'Person C', name_key: 'person c' },
		{ ...FOCUS_PERSON, id: 5, name: 'Person D', name_key: 'person d' }
	];
	const { target, text } = renderPage(
		pageSettings({ digest_focus_person_id: 7 }),
		[FOCUS_PERSON, other, ...watched]
	);
	const select = target.querySelector<HTMLSelectElement>('#set-focus-person');
	expect(select).not.toBeNull();
	expect(new FormData(select!.form!).getAll('watchlist')).toEqual(['2', '5']);
	flushSync(() => {
		select!.value = '8';
		select!.dispatchEvent(new Event('change', { bubbles: true }));
	});
	expect(new FormData(select!.form!).getAll('digest_focus_person_id')).toEqual(['8']);
	expect(new FormData(select!.form!).getAll('watchlist')).toEqual(['2', '5']);
	expect(text()).toContain('Cambios pendientes de guardar');
	flushSync(() => {
		select!.value = '';
		select!.dispatchEvent(new Event('change', { bubbles: true }));
	});
	expect(new FormData(select!.form!).getAll('digest_focus_person_id')).toEqual(['']);
	expect(new FormData(select!.form!).getAll('watchlist')).toEqual(['2', '5']);
});

it('preserves the principal when the loaded catalog does not contain it', () => {
	const { target } = renderPage(pageSettings({ digest_focus_person_id: 7 }), []);
	const select = target.querySelector<HTMLSelectElement>('#set-focus-person')!;
	expect(select.value).toBe('7');
	expect(select.selectedOptions[0].textContent).toContain('no disponible');
	expect(select.selectedOptions[0].disabled).toBe(false);
	expect(new FormData(select.form!).getAll('digest_focus_person_id')).toEqual(['7']);
});

it('renders the v3 tab strip with one visible panel and the savebar', () => {
	const { target } = renderPage(pageSettings());

	const tabs = [...target.querySelectorAll('.config-tabs button')] as HTMLButtonElement[];
	expect(tabs.map((tab) => tab.textContent?.trim())).toEqual([
		'Palabras clave',
		'Operación',
		'Fuentes',
		'LLM'
	]);
	expect(tabs[0]?.getAttribute('aria-current')).toBe('page');

	// Every section stays mounted; exactly one is visible per tab.
	const panelIds = ['palabras-clave', 'operacion', 'fuentes', 'llm'];
	const visible = panelIds.filter((id) => !target.querySelector(`#${id}`)?.hasAttribute('hidden'));
	expect(visible).toEqual(['palabras-clave']);
	// Hidden panels keep their controls mounted for the save payload.
	expect(target.querySelector('#operacion input[name="retention_days"]')).toBeInstanceOf(
		HTMLInputElement
	);
	expect(target.querySelector('#llm input[name="ai_model"]')).toBeInstanceOf(HTMLInputElement);

	const savebar = target.querySelector('.config-savebar');
	expect(savebar?.textContent).toContain('Sin cambios pendientes');
	expect(target.querySelector('button[form="settings-save"]')).toBeInstanceOf(HTMLButtonElement);

	flushSync(() => tabs[2]?.click());
	expect(target.querySelector('#operacion')?.hasAttribute('hidden')).toBe(true);
	expect(target.querySelector('#fuentes')?.hasAttribute('hidden')).toBe(false);
});

it('discard restores the loaded values and clears the pending flag', () => {
	const confirm = window.confirm;
	window.confirm = () => true;
	try {
		const { target } = renderPage(pageSettings({ digest_focus_person_id: 7 }), [FOCUS_PERSON]);
		const select = target.querySelector<HTMLSelectElement>('#set-focus-person')!;
		flushSync(() => {
			select.value = '8';
			select.dispatchEvent(new Event('change', { bubbles: true }));
		});
		expect(target.querySelector('.config-savebar')?.textContent).toContain(
			'Cambios pendientes de guardar'
		);

		const discard = target.querySelector<HTMLButtonElement>(
			'.config-savebar button[type="button"]'
		)!;
		flushSync(() => discard.click());

		expect(select.value).toBe('7');
		expect(target.querySelector('.config-savebar')?.textContent).toContain(
			'Sin cambios pendientes'
		);
	} finally {
		window.confirm = confirm;
	}
});

it('offers a credential-free saved reviewer connection test without changing save ownership', () => {
	const { target, text } = renderPage(pageSettings({ digest_reviewer_provider: 'openai',
		digest_reviewer_base_url: 'https://reviewer.invalid/v1', digest_reviewer_model: 'fixture-reviewer',
		digest_reviewer_api_key_set: true }));
	clickLabeled(target, '.config-tabs button', 'LLM');
	const button = target.querySelector<HTMLButtonElement>('button[form="reviewer-probe"]');
	expect(button).toBeInstanceOf(HTMLButtonElement);
	expect(button!.textContent).toBe('Probar conexión');
	const probe = target.querySelector<HTMLFormElement>('form[action="?/test-reviewer"]')!;
	expect(probe.method).toBe('post');
	expect(button!.form).toBe(probe);
	expect([...new FormData(probe).keys()]).toEqual([]);
	expect(target.querySelector('form form')).toBeNull();
	expect(button!.disabled).toBe(false);
	const save = target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]')!;
	expect(save.querySelector<HTMLButtonElement>('button[type="submit"]')!.form).toBe(save);
	expect(text()).toContain('Guarda los cambios antes de probar; se usa la configuración guardada.');
	expect(text()).toContain('puede generar un costo');
});

const REVIEWER_NAMES = ['digest_reviewer_api_key', 'digest_reviewer_base_url', 'digest_reviewer_guided_mode', 'digest_reviewer_model', 'digest_reviewer_provider'];

it('offers the reviewer guided-mode selector bound to the saved value', () => {
	const { target } = renderPage(pageSettings({ digest_reviewer_provider: 'openai',
		digest_reviewer_guided_mode: 'json_object' }));
	clickLabeled(target, '.config-tabs button', 'LLM');
	const select = target.querySelector<HTMLSelectElement>('[name="digest_reviewer_guided_mode"]');
	expect(select).toBeInstanceOf(HTMLSelectElement);
	expect(select!.value).toBe('json_object');
	expect([...select!.options].map((o) => o.value).sort()).toEqual(['json_object', 'json_schema', 'plain']);
	expect(target.textContent).toContain('Usa json_object cuando el proveedor no admita json_schema');
});

it('renders an independent reviewer form under LLM with exactly five safe controls', () => {
	const { target } = renderPage(pageSettings({ digest_reviewer_provider: 'openai',
		digest_reviewer_base_url: 'https://reviewer.invalid/v1', digest_reviewer_model: 'fixture-reviewer',
		digest_reviewer_api_key: 'fixture-only-must-not-render', digest_reviewer_api_key_set: true }));
	clickLabeled(target, '.config-tabs button', 'LLM');
	const reviewer = target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]');
	expect(reviewer).toBeInstanceOf(HTMLFormElement);
	expect(reviewer!.hidden).toBe(false);
	expect(reviewer!.textContent).toContain('Revisor de informes');
	expect(reviewer!.parentElement?.classList.contains('config-body')).toBe(true);
	expect(reviewer!.parentElement?.closest('form')).toBeNull();
	expect(target.querySelector('form form')).toBeNull();
	expect([...new FormData(reviewer!).keys()].sort()).toEqual(REVIEWER_NAMES);
	expect(new FormData(reviewer!).get('digest_reviewer_api_key')).toBe('');
	expect(reviewer!.querySelector<HTMLInputElement>('[name="digest_reviewer_api_key"]')?.type).toBe('password');
	expect(reviewer!.textContent).toContain('Clave del revisor guardada');
	expect(target.innerHTML).not.toContain('fixture-only-must-not-render');
	expect(reviewer!.querySelector('[formaction]')).toBeNull();
	const general = target.querySelector<HTMLFormElement>('form[action="?/save"]')!;
	expect([...new FormData(general).keys()].some((name) => name.startsWith('digest_reviewer_'))).toBe(false);
	expect(general.querySelector('[formaction="?/test-ai"]')).not.toBeNull();
	clickLabeled(target, '.config-tabs button', 'Operación');
	expect(reviewer!.hidden).toBe(true);
	expect([...new FormData(reviewer!).keys()].sort()).toEqual(REVIEWER_NAMES);
	expect(general.querySelector('[name="ai_model"]')).not.toBeNull();
	expect(target.querySelector('.config-savebar')?.textContent).toContain('Sin cambios pendientes');
});

function editControl(target: ParentNode, name: string, value: string): void {
	const input = target.querySelector<HTMLInputElement | HTMLSelectElement>(`[name="${name}"]`)!;
	flushSync(() => {
		input.value = value;
		input.dispatchEvent(new Event(input instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
	});
}

it.each(['success', 'failure', 'error', 'redirect', 'throw'])('clears only the reviewer secret after %s and releases its own pending state', async (kind) => {
	const initial = pageSettings({ ai_model: 'fixture-generator', digest_reviewer_provider: 'openai' });
	const { target, refresh } = renderPage(initial);
	clickLabeled(target, '.config-tabs button', 'LLM');
	editControl(target, 'ai_model', 'unsaved-generator');
	editControl(target, 'digest_reviewer_model', 'unsaved-reviewer');
	editControl(target, 'digest_reviewer_base_url', 'https://draft.invalid/v1');
	editControl(target, 'digest_reviewer_api_key', 'fixture-only-submitted-key');
	const reviewer = target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]')!;
	const submit = enhanced.get(reviewer);
	expect(submit).toBeTypeOf('function');
	let pendingCallback: ReturnType<SubmitFunction>;
	flushSync(() => { pendingCallback = submit!({ formElement: reviewer, formData: new FormData(reviewer) } as never); });
	const callback = await pendingCallback!;
	expect(callback).toBeTypeOf('function');
	if (typeof callback !== 'function') throw new Error('Reviewer submit callback missing');
	expect(reviewer.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
	expect(target.querySelector<HTMLButtonElement>('button[form="settings-save"]')!.disabled).toBe(false);
	const message = kind === 'success' ? 'Configuración del revisor guardada.' : 'No se pudo guardar el revisor. Revisa el modo, la URL y el modelo.';
	const actionData = { action: 'save-reviewer', ok: kind === 'success', message,
		engine: null, model: null, latency_ms: null, status_code: null, error_code: null, label: null } as const;
	const update = vi.fn(async () => {
		if (kind === 'throw') throw new Error('fixture-only-submitted-key');
		refresh({ ...initial, ai_model: 'refetched-generator', digest_reviewer_api_key_set: true }, actionData);
	});
	await expect(callback({
		update, result: { type: kind === 'throw' ? 'success' : kind, status: kind === 'failure' ? 422 : 200, data: actionData }
	} as never)).resolves.toBeUndefined();
	flushSync();
	expect(update).toHaveBeenCalledWith({ reset: false });
	expect(new FormData(reviewer).get('digest_reviewer_api_key')).toBe('');
	expect(new FormData(reviewer).get('digest_reviewer_model')).toBe('unsaved-reviewer');
	expect(new FormData(reviewer).get('digest_reviewer_base_url')).toBe('https://draft.invalid/v1');
	expect(reviewer.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(false);
	expect(target.querySelector<HTMLInputElement>('[name="ai_model"]')!.value).toBe('unsaved-generator');
	expect(target.querySelector('.config-savebar')?.textContent).toContain('Cambios pendientes de guardar');
	expect(reviewer.querySelector('[role="status"], [role="alert"]')?.textContent).toContain(kind === 'throw'
		? 'No se pudo actualizar la pantalla del revisor. Vuelve a intentarlo.' : message);
	expect(target.querySelectorAll('.config-feedback')).toHaveLength(1);
	expect(target.textContent).not.toContain('fixture-only-submitted-key');
	clickLabeled(target, '.config-tabs button', 'Fuentes');
	clickLabeled(target, '.config-tabs button', 'LLM');
	expect(target.querySelector<HTMLInputElement>('[name="ai_model"]')!.value).toBe('unsaved-generator');
});

it.each(['digest_reviewer_provider', 'digest_reviewer_base_url', 'digest_reviewer_model', 'digest_reviewer_api_key', 'digest_reviewer_guided_mode'])('requires saving reviewer draft %s before testing', (field) => {
	const { target } = renderPage(pageSettings({ digest_reviewer_provider: 'openai',
		digest_reviewer_base_url: 'https://saved.invalid/v1', digest_reviewer_model: 'saved-model' }));
	clickLabeled(target, '.config-tabs button', 'LLM');
	expect(target.querySelector<HTMLButtonElement>('button[form="reviewer-probe"]')!.disabled).toBe(false);
	editControl(target, field, field === 'digest_reviewer_provider' ? 'inherit'
		: field === 'digest_reviewer_guided_mode' ? 'json_object' : 'unsaved-value');
	expect(target.querySelector<HTMLButtonElement>('button[form="reviewer-probe"]')!.disabled).toBe(true);
	const probe = target.querySelector<HTMLFormElement>('form[action="?/test-reviewer"]')!;
	expect([...new FormData(probe).keys()]).toEqual([]);
	expect(target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]')!.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(false);
});

it.each(['success', 'failure', 'error', 'redirect', 'throw'])('releases reviewer probe state after %s without resetting general drafts', async (kind) => {
	const initial = pageSettings({ ai_model: 'saved-generator' });
	const { target, refresh } = renderPage(initial);
	clickLabeled(target, '.config-tabs button', 'LLM');
	editControl(target, 'ai_model', 'unsaved-generator');
	const probe = target.querySelector<HTMLFormElement>('form[action="?/test-reviewer"]')!;
	const button = target.querySelector<HTMLButtonElement>('button[form="reviewer-probe"]')!;
	const save = target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]')!;
	expect(button.disabled).toBe(false);
	const submit = enhanced.get(probe)!;
	let pending: ReturnType<SubmitFunction>;
	flushSync(() => { pending = submit({ formElement: probe, formData: new FormData(probe) } as never); });
	const callback = await pending!;
	if (typeof callback !== 'function') throw new Error('Probe callback missing');
	expect(button.disabled).toBe(true);
	expect(button.textContent).toBe('Probando…');
	expect(save.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(true);
	const actionData = { action: 'test-reviewer', ok: kind === 'success', message: 'Resultado de prueba.',
		engine: null, model: null, latency_ms: 12, status_code: null, error_code: null, label: null } as const;
	const update = vi.fn(async () => {
		if (kind === 'throw') throw new Error('synthetic-do-not-display');
		refresh({ ...initial, ai_model: 'refetched-generator' }, actionData);
	});
	await expect(callback({ update, result: { type: kind === 'throw' ? 'success' : kind, status: 200, data: actionData } } as never)).resolves.toBeUndefined();
	flushSync();
	expect(update).toHaveBeenCalledWith({ reset: false, invalidateAll: false });
	expect(button.disabled).toBe(false);
	expect(save.querySelector<HTMLButtonElement>('button[type="submit"]')!.disabled).toBe(false);
	expect(target.querySelector<HTMLInputElement>('[name="ai_model"]')!.value).toBe('unsaved-generator');
	expect(target.textContent).not.toContain('synthetic-do-not-display');
	expect(save.querySelector('[role="status"], [role="alert"]')?.textContent).toContain(kind === 'throw'
		? 'No se pudo actualizar la prueba del revisor. Vuelve a intentarlo.' : 'Resultado de prueba.');
});

it.each([false, true])('shows a saved reviewer password indicator without submitting it (stored=%s)', (stored) => {
	const initial = pageSettings({ digest_reviewer_api_key_set: stored });
	const { target, refresh } = renderPage(initial);
	clickLabeled(target, '.config-tabs button', 'LLM');
	const form = target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]')!;
	const field = form.querySelector<HTMLInputElement>('[name="digest_reviewer_api_key"]')!;
	expect(field.type).toBe('password');
	expect(field.placeholder).toBe(stored ? '••••••••' : 'Sin clave guardada');
	expect(field.value).toBe('');
	expect(new FormData(form).get('digest_reviewer_api_key')).toBe('');
	editControl(target, 'digest_reviewer_api_key', 'synthetic-replacement');
	expect(field.type).toBe('password');
	expect(new FormData(form).get('digest_reviewer_api_key')).toBe('synthetic-replacement');
	editControl(target, 'digest_reviewer_api_key', '');
	refresh({ ...initial, digest_reviewer_api_key_set: !stored });
	expect(field.placeholder).toBe(stored ? 'Sin clave guardada' : '••••••••');
	expect(field.value).toBe('');
	expect(new FormData(form).get('digest_reviewer_api_key')).toBe('');
});

it('renders non-secret provider diagnostics only when present', () => {
	const settings = pageSettings({ digest_reviewer_provider: 'openai' });
	const { target, text, refresh } = renderPage(settings);
	clickLabeled(target, '.config-tabs button', 'LLM');
	refresh(settings, { action: 'test-reviewer', ok: false,
		message: 'El proveedor rechazó la prueba; revisa el modelo y la URL base.',
		engine: null, model: null, latency_ms: 458, label: null,
		status_code: null, error_code: null } as never);
	expect(text()).not.toContain('Diagnóstico del proveedor');
	refresh(settings, { action: 'test-reviewer', ok: false,
		message: 'El proveedor rechazó la prueba; revisa el modelo y la URL base.',
		engine: null, model: null, latency_ms: 458, label: null,
		status_code: 400, error_code: 'Model Not Exist' } as never);
	expect(text()).toContain('Diagnóstico del proveedor: HTTP 400 · Model Not Exist.');
	expect(text()).toContain('Tiempo de respuesta: 458 ms.');
});

it('warns before saving when the reviewer URL already includes /chat/completions', () => {
	const { target, text } = renderPage(pageSettings({ digest_reviewer_provider: 'openai',
		digest_reviewer_base_url: 'https://api.example.com/v1' }));
	clickLabeled(target, '.config-tabs button', 'LLM');
	expect(text()).not.toContain('La URL ya incluye');
	editControl(target, 'digest_reviewer_base_url', 'https://api.example.com/v1/chat/completions');
	expect(text()).toContain('La URL ya incluye /chat/completions; guarda solo la URL base del servicio.');
	editControl(target, 'digest_reviewer_base_url', 'https://api.example.com/v1');
	expect(text()).not.toContain('La URL ya incluye');
});

it('keeps reviewer edits independent from the general savebar and defaults to inheritance', () => {
	const { target } = renderPage(pageSettings());
	clickLabeled(target, '.config-tabs button', 'LLM');
	const reviewer = target.querySelector<HTMLFormElement>('form[action="?/save-reviewer"]')!;
	expect(new FormData(reviewer).get('digest_reviewer_provider')).toBe('inherit');
	editControl(reviewer, 'digest_reviewer_model', 'reviewer-draft');
	expect(target.querySelector('.config-savebar')?.textContent).toContain('Sin cambios pendientes');
	editControl(reviewer, 'digest_reviewer_provider', 'openai');
	expect(reviewer.textContent).toContain('Una configuración incompleta no utiliza las credenciales generales');
	expect([...new FormData(reviewer).keys()].sort()).toEqual(REVIEWER_NAMES);
});

it('ignores the legacy keyword focus and keeps keyword CRUD independent', () => {
	const key = 'media-monitor-keyword-focus';
	// jsdom 29 + node 26 ships no window.localStorage under vitest; the legacy
	// marker is simulation only — the page reads no storage of its own.
	const storage = window.localStorage ?? null;
	const before = storage?.getItem(key) ?? null;
	storage?.setItem(key, 'An unrelated keyword');
	try {
		const keywords: Keyword[] = [
			{
				id: 1,
				text: 'An unrelated keyword',
				language: 'es',
				is_active: true,
				created_at: '2026-10-25T12:00:00Z'
			}
		];
		const { target, text } = renderPage(
			pageSettings({ digest_focus_person_id: 7 }),
			[FOCUS_PERSON],
			keywords
		);
		const select = target.querySelector<HTMLSelectElement>('#set-focus-person')!;
		expect(select.value).toBe('7');
		expect(target.querySelector('.config-keyword-table tbody tr')?.textContent).toContain(keywords[0].text);
		expect(text()).not.toContain('Fijar como foco');
		expect(text()).not.toContain('Quitar foco');
		// The directory note mentions the summary focus, but no per-keyword
		// focus action may exist (mock «Foco del resumen» button).
		const actionLabels = [...target.querySelectorAll('.config-keyword-actions button')].map(
			(button) => button.textContent?.trim()
		);
		expect(actionLabels).toEqual(['Desactivar', 'Eliminar']);
		expect(target.querySelector('.keyword-focus-badge')).toBeNull();
		const create = target.querySelector<HTMLFormElement>('form[action="?/create"]')!;
		const term = create.elements.namedItem('text') as HTMLInputElement;
		term.value = 'Another search term';
		flushSync(() => {
			select.value = '';
			select.dispatchEvent(new Event('change', { bubbles: true }));
		});
		expect(new FormData(select.form!).getAll('digest_focus_person_id')).toEqual(['']);
		expect(new FormData(create).get('text')).toBe('Another search term');
		expect(create.closest('form[action="?/save"]')).toBeNull();
		const toggle = target.querySelector<HTMLFormElement>('form[action="?/toggle"]')!;
		expect(new FormData(toggle).get('id')).toBe('1');
		expect(new FormData(toggle).get('is_active')).toBe('0');
		const remove = target.querySelector<HTMLFormElement>('form[action="?/delete"]')!;
		expect(new FormData(remove).get('id')).toBe('1');
		expect(target.querySelectorAll('.config-keyword-table tbody tr')).toHaveLength(1);
		if (storage) expect(storage.getItem(key)).toBe(keywords[0].text);
	} finally {
		if (storage) {
			if (before === null) storage.removeItem(key);
			else storage.setItem(key, before);
		}
	}
});
