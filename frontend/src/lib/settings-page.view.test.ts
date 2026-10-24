// @vitest-environment jsdom
import { flushSync, mount, unmount } from 'svelte';
import { afterEach, expect, it } from 'vitest';

import type { ClientSettings } from '$lib/api';

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
	x_mode: 'free',
	x_api_key: '',
	x_api_key_set: false,
	updated_at: '2026-10-22T03:00:00Z'
};

function pageSettings(overrides: Partial<ClientSettings> = {}): ClientSettings {
	return { ...SETTINGS_VIEW, ...overrides };
}

const mounted: Array<Record<string, unknown>> = [];

function renderPage(settings: ClientSettings): { text: () => string } {
	const target = document.createElement('div');
	document.body.appendChild(target);
	const instance = mount(SettingsPage, {
		target,
		props: { params: {}, data: { settings, scrapersAvailable: [], keywords: [], persons: [] }, form: null }
	});
	mounted.push(instance as unknown as Record<string, unknown>);
	// Markup wraps lines: collapse whitespace so copy asserts survive reflows.
	return { text: () => (target.textContent ?? '').replace(/\s+/g, ' ') };
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
