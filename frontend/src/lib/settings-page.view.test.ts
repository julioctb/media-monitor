// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { ClientSettings, Keyword, PersonSummary } from '$lib/api';

import SettingsPage from '../routes/settings/+page.svelte';

/**
 * Settings page view: the X section's mode switch drives the free-mode
 * limitations banner and the masked-key status line. The banner must
 * react to the radio WITHOUT a save (mirror of the mockup's provider
 * panel, which toggles on selection).
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

afterEach(() => {
	while (mounted.length) void unmount(mounted.pop() as never);
});

const BANNER_HEAD = 'Modo gratuito: las menciones de X provienen del índice de Google News';
const FALLBACK_NOTE = 'Sin key: se usará el modo gratuito como respaldo';

it('shows the free limitations banner and hides the paid-only key field', () => {
	const { text } = renderPage(pageSettings({ x_mode: 'free', x_api_key_set: true }));

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
	const { text } = renderPage(pageSettings({ x_mode: 'paid', x_api_key_set: false }));

	expect(text()).not.toContain(BANNER_HEAD);
	expect(text()).not.toContain('API key guardada');
	expect(text()).toContain(FALLBACK_NOTE);
	// Paid mode reveals the key field.
	expect(document.querySelector('input#x-api-key')).toBeInstanceOf(HTMLInputElement);
});

it('reveals the banner as soon as free is selected, without saving', () => {
	const { text } = renderPage(pageSettings({ x_mode: 'paid', x_api_key_set: false }));
	const target = document.querySelector('input[name="x_mode"][value="free"]');
	expect(target).toBeInstanceOf(HTMLInputElement);

	const free = target as HTMLInputElement;
	free.checked = true;
	free.dispatchEvent(new Event('change', { bubbles: true }));
	flushSync();

	expect(text()).toContain(BANNER_HEAD);
	expect(text()).not.toContain(FALLBACK_NOTE); // the fallback note is paid-conditional
	expect(document.querySelector('input#x-api-key')).toBeNull(); // so is the field
});

it('reveals the API key field only under paid, without saving', () => {
	const { text } = renderPage(pageSettings({ x_mode: 'free', x_api_key_set: true }));
	expect(document.querySelector('input#x-api-key')).toBeNull();

	const paid = document.querySelector('input[name="x_mode"][value="paid"]') as HTMLInputElement;
	paid.checked = true;
	paid.dispatchEvent(new Event('change', { bubbles: true }));
	flushSync();

	expect(document.querySelector('input#x-api-key')).toBeInstanceOf(HTMLInputElement);
	expect(text()).toContain('API key guardada');
	expect(text()).not.toContain(BANNER_HEAD);
});


it('renders the v2 schedule selects and preserves hidden settings', () => {
	const { text } = renderPage(
		pageSettings({ digest_hours: [8, 21], gdelt_enabled: true, enrich_max_per_cycle: 40 })
	);

	expect(text()).toContain('Horarios del resumen diario');
	const selects = [
		...document.querySelectorAll('select[name="digest_hour"]')
	] as HTMLSelectElement[];
	expect(selects.map((select) => select.value)).toEqual(['8', '21']);
	expect(text()).toContain('Los horarios usan la hora de Ciudad de México');

	// Preserved fields travel hidden on every save.
	const hidden = (name: string) =>
		document.querySelector(`input[name="${name}"]`) as HTMLInputElement | null;
	expect(hidden('timezone')?.value).toBe('America/Mexico_City');
	expect(hidden('enrich_max_per_cycle')?.value).toBe('40');
	expect(hidden('gdelt_enabled')?.value).toBe('1');
	expect(hidden('facebook_pages')).toBeInstanceOf(HTMLInputElement);
});

it('renders facebook draft rows with count and pagination chrome', () => {
	renderPage(
		pageSettings({
			facebook_pages: [
				{ page_id: '61593006365773', label: 'Buapachosos' },
				{ page_id: '10006932572555', label: '' }
			]
		})
	);

	const rows = [...document.querySelectorAll('.facebook-table tbody tr')];
	expect(rows.length).toBe(2);
	expect(rows[0].textContent).toContain('Buapachosos');
	expect(rows[1].textContent).toContain('Sin etiqueta');
	expect(document.querySelector('.facebook-count')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
		'2 fuentes'
	);
	expect(document.querySelector('.facebook-pagination')?.textContent).toContain('Página 1 de 1');
	// The serialized payload carries normalized refs for the save action.
	const payload = JSON.parse(
		(document.querySelector('input[name="facebook_pages"]') as HTMLInputElement).value
	) as { page_id: string }[];
	expect(payload.map((page) => page.page_id)).toEqual(['61593006365773', '10006932572555']);
});

it('renders planned social cards and the rss source list', () => {
	renderPage(pageSettings({ rss_feeds: ['https://ejemplo.com/feed.xml'] }));

	const text = () => document.body.textContent ?? '';
	expect(text()).toContain('TikTok');
	expect(text()).toContain('Instagram');
	expect(document.querySelector('.source-item-url')?.textContent).toBe(
		'https://ejemplo.com/feed.xml'
	);
	const rssList = document.querySelector('[aria-label="Feeds RSS"]');
	expect(rssList?.querySelector('.source-empty')).toBeNull();
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
	expect(select!.closest('#operacion .field-grid')).not.toBeNull();
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
	expect(text()).toContain('Guardar configuración (cambios sin guardar)');
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
		expect(target.querySelector('.keywords tbody tr')?.textContent).toContain(keywords[0].text);
		expect(text()).not.toContain('Fijar como foco');
		expect(text()).not.toContain('Quitar foco');
		expect(text()).not.toContain('foco del resumen');
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
		expect(target.querySelectorAll('.keywords tbody tr')).toHaveLength(1);
		expect(localStorage.getItem(key)).toBe(keywords[0].text);
	} finally {
		if (before === null) localStorage.removeItem(key);
		else localStorage.setItem(key, before);
	}
});
