// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';

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
): { text: () => string; target: HTMLDivElement } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(SettingsPage, {
		target,
		props: { params: {}, data: { settings, scrapersAvailable: [], keywords, persons }, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	// Flush initial bindings/effects before inspecting or interacting with controls.
	flushSync();
	// Markup wraps lines: collapse whitespace so copy asserts survive reflows.
	return { text: () => (target.textContent ?? '').replace(/\s+/g, ' '), target };
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

it('ignores the legacy keyword focus and keeps keyword CRUD independent', () => {
	const key = 'media-monitor-keyword-focus';
	const before = localStorage.getItem(key);
	localStorage.setItem(key, 'An unrelated keyword');
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
		expect(localStorage.getItem(key)).toBe(keywords[0].text);
	} finally {
		if (before === null) localStorage.removeItem(key);
		else localStorage.setItem(key, before);
	}
});
