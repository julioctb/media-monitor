<script lang="ts">
	import { onMount } from 'svelte';

	import { enhance } from '$app/forms';

	import KeywordsPanel from '$lib/components/KeywordsPanel.svelte';
	import { BTN_PRIMARY_CLS, INPUT_CLS } from '$lib/ui';
	import { ICON_PATHS } from '$lib/icons';
	import type { AvailableScraper, ClientSettings, XMode } from '$lib/api';
	import { normalizeFacebookPageRef } from '$lib/facebook-page';
	import type { PageProps, SubmitFunction } from './$types';

	let { data, form }: PageProps = $props();

	const LABEL_CLS = 'field-label';
	const CHECK_CLS = 'size-4 rounded border-line accent-accent';
	/** Dialog-only action skin (the directories carry their own button system). */
	const SMALL_BTN_CLS =
		'inline-flex min-h-[36px] items-center justify-center rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-ink-2 transition-colors hover:bg-surface-warm disabled:opacity-60';

	/** Upper bound of daily digest cuts; mirrors the backend validator. */
	const MAX_DIGEST_HOURS = 8;

	/** Rows per source-directory page (mockup settings.js contract). */
	const DIRECTORY_PAGE_SIZE = 10;

	// Keyword CRUD is embedded below via KeywordsPanel; its actions live in
	// this page's server module.

	/** One ingest source: the Facebook URL as typed, plus its optional label. */
	interface PageDraft {
		url: string;
		label: string;
	}

	interface SettingsDraft {
		timezone: string;
		/** Kept as text: the action parses it, '' surfaces a friendly error. */
		retention_days: string;
		/** Daily digest cut hours, 1..8 entries in 0..23. */
		digest_hours: number[];
		/** Principal monitored person id as text; '' = none (null on the API). */
		focus_person_id: string;
		/** Worker per-cycle caps, text like retention_days. Preserved hidden. */
		enrich_max: string;
		fetch_max: string;
		gdelt_enabled: boolean;
		pages: PageDraft[];
		/** RSS feed URLs, one entry per source. */
		rss: string[];
		/** Enabled scraper names (subset of data.scrapersAvailable). */
		scrapers: string[];
		ai_provider: 'local' | 'openai';
		ai_base_url: string;
		ai_model: string;
		ai_model_fast: string;
		ai_api_key: string;
	}

	function toDraft(settings: ClientSettings): SettingsDraft {
		return {
			timezone: settings.timezone,
			retention_days: String(settings.retention_days),
			digest_hours: [...settings.digest_hours],
			focus_person_id:
				settings.digest_focus_person_id === null
					? ''
					: String(settings.digest_focus_person_id),
			enrich_max: String(settings.enrich_max_per_cycle),
			fetch_max: String(settings.fetch_max_per_cycle),
			gdelt_enabled: settings.gdelt_enabled,
			pages: settings.facebook_pages.map((page) => ({
				url: `facebook.com/${page.page_id}`,
				label: page.label
			})),
			rss: [...settings.rss_feeds],
			scrapers: [...settings.scrapers],
			ai_provider: settings.ai_provider,
			ai_base_url: settings.ai_base_url ?? '',
			ai_model: settings.ai_model ?? '',
			ai_model_fast: settings.ai_model_fast ?? '',
			ai_api_key: settings.ai_api_key ?? ''
		};
	}

	// Intentional snapshot: the draft starts from the loaded row and is then
	// edited in place; later `data` updates must not clobber the form.
	// svelte-ignore state_referenced_locally
	let draft = $state<SettingsDraft>(toDraft(data.settings));
	let dirty = $state(false);
	let submitting = $state(false);

	// X mode snapshot: like `draft`, a local edit surface published by its
	// save; `data` refreshes must not revert an unsaved selection.
	// svelte-ignore state_referenced_locally
	let xMode: XMode = $state(data.settings.x_mode);
	/** Gates the X section's submit while its request is in flight. */
	let xSaving = $state(false);

	/* ------------------------- Config workspace tabs ------------------------- */
	// Tab ids mirror the section anchors, so old #hash deep links keep working.
	const TABS = [
		{ id: 'keywords', label: 'Palabras clave' },
		{ id: 'operacion', label: 'Operación' },
		{ id: 'fuentes', label: 'Fuentes' },
		{ id: 'llm', label: 'LLM' }
	] as const;

	type TabId = (typeof TABS)[number]['id'];

	/** One visible panel at a time (mockup config-workspace); client-side only. */
	let activeTab: TabId = $state('keywords');

	onMount(() => {
		const hash = window.location.hash.slice(1);
		if (TABS.some((tab) => tab.id === hash)) activeTab = hash as TabId;
	});

	function selectTab(tab: TabId): void {
		activeTab = tab;
		// Keeps the panel deep-linkable without jumping the scroll position.
		window.history.replaceState(null, '', `#${tab}`);
	}

	// Registry snapshot from the load: toggles write to `draft`, never to
	// page data. Intentional snapshot, like `draft` above.
	// svelte-ignore state_referenced_locally
	const availableScrapers: AvailableScraper[] = data.scrapersAvailable ?? [];

	function toggleScraper(name: string, checked: boolean): void {
		draft.scrapers = checked
			? [...draft.scrapers, name]
			: draft.scrapers.filter((entry) => entry !== name);
	}

	/** Clamp 0..23 on input; '' keeps the old value until a digit lands. */
	function setDigestHour(index: number, raw: string): void {
		const value = Number.parseInt(raw, 10);
		if (Number.isNaN(value)) return;
		draft.digest_hours[index] = Math.max(0, Math.min(23, value));
		dirty = true;
	}

	function addDigestHour(): void {
		if (draft.digest_hours.length >= MAX_DIGEST_HOURS) return;
		// First hour not configured yet, so duplicates never pile up.
		for (let hour = 0; hour <= 23; hour += 1) {
			if (!draft.digest_hours.includes(hour)) {
				draft.digest_hours.push(hour);
				break;
			}
		}
		dirty = true;
	}

	function removeDigestHour(index: number): void {
		if (draft.digest_hours.length <= 1) return; // always >= 1 cut
		draft.digest_hours.splice(index, 1);
		dirty = true;
	}

	function markDirty(): void {
		dirty = true;
	}

	/* --------------------------- Source directories -------------------------- */
	// Fuentes contract (mockup settings.js configSources): two-level sub-nav
	// and ONE tabular directory at a time — not the stacked source cards.

	type SourceKind = 'rss' | 'scraper' | 'facebook';
	type SourceTab = 'rss' | 'scraper' | 'social';
	type SocialTab = 'facebook' | 'twitter' | 'tiktok' | 'instagram';

	let sourceTab = $state<SourceTab>('rss');
	let socialTab = $state<SocialTab>('facebook');
	/** Shared query; the mockup clears it when switching sub-tabs. */
	let sourceQuery = $state('');
	let rssPage = $state(1);
	let scraperPage = $state(1);
	let fbPage = $state(1);

	const SOURCE_TABS: ReadonlyArray<readonly [SourceTab, string]> = [
		['rss', 'Feed RSS'],
		['scraper', 'Scrapers'],
		['social', 'Redes sociales']
	];

	const SOCIAL_TABS: ReadonlyArray<readonly [SocialTab, string]> = [
		['facebook', 'Facebook'],
		['twitter', 'Twitter / X'],
		['tiktok', 'TikTok'],
		['instagram', 'Instagram']
	];

	const DIRECTORY_META: Record<
		SourceKind,
		{ title: string; copy: string; urlCol: string; add: string | null; tableLabel: string }
	> = {
		rss: {
			title: 'Feed RSS',
			copy: 'Administra los feeds de noticias del monitoreo.',
			urlCol: 'URL del feed',
			add: 'Añadir feed',
			tableLabel: 'Fuentes RSS del monitoreo'
		},
		scraper: {
			title: 'Scrapers',
			copy: 'Administra los sitios de noticias sin RSS.',
			urlCol: 'URL del sitio',
			add: null,
			tableLabel: 'Scrapers del monitoreo'
		},
		facebook: {
			title: 'Páginas de Facebook',
			copy: 'Administra las páginas del monitoreo. Los cambios se aplican al guardar.',
			urlCol: 'URL de la página',
			add: 'Añadir página',
			tableLabel: 'Páginas de Facebook del monitoreo'
		}
	};

	function selectSourceTab(tab: SourceTab): void {
		sourceTab = tab;
		resetDirectoryState();
	}

	function selectSocialTab(tab: SocialTab): void {
		socialTab = tab;
		resetDirectoryState();
	}

	function resetDirectoryState(): void {
		sourceQuery = '';
		resetDirectoryPages();
	}

	function resetDirectoryPages(): void {
		rssPage = 1;
		scraperPage = 1;
		fbPage = 1;
	}

	/** Directory shown for the active sub-tab; null for social non-Facebook. */
	const directoryType = $derived<SourceKind | null>(
		sourceTab === 'social' ? (socialTab === 'facebook' ? 'facebook' : null) : sourceTab
	);

	/** Directory display name for an RSS URL: the feed's host. */
	function rssName(url: string): string {
		try {
			return new URL(url).hostname.replace(/^www\./, '');
		} catch {
			return url;
		}
	}

	function matchesQuery(...fields: string[]): boolean {
		const query = sourceQuery.trim().toLocaleLowerCase('es');
		return query === '' || fields.join(' ').toLocaleLowerCase('es').includes(query);
	}

	/** Draft rows matching the search, in draft order. */
	const filteredRss = $derived(
		draft.rss
			.map((url, index) => ({ url, index }))
			.filter(({ url }) => matchesQuery(rssName(url), url))
	);
	const rssPageCount = $derived(Math.max(1, Math.ceil(filteredRss.length / DIRECTORY_PAGE_SIZE)));
	const pagedRss = $derived(
		filteredRss.slice((rssPage - 1) * DIRECTORY_PAGE_SIZE, rssPage * DIRECTORY_PAGE_SIZE)
	);

	const filteredScrapers = $derived(
		availableScrapers.filter((scraper) => matchesQuery(scraper.name, scraper.base_url))
	);
	const scraperPageCount = $derived(
		Math.max(1, Math.ceil(filteredScrapers.length / DIRECTORY_PAGE_SIZE))
	);
	const pagedScrapers = $derived(
		filteredScrapers.slice(
			(scraperPage - 1) * DIRECTORY_PAGE_SIZE,
			scraperPage * DIRECTORY_PAGE_SIZE
		)
	);

	const filteredPages = $derived(
		draft.pages
			.map((page, index) => ({ page, index }))
			.filter(({ page }) => matchesQuery(page.label, page.url))
	);
	const fbPageCount = $derived(Math.max(1, Math.ceil(filteredPages.length / DIRECTORY_PAGE_SIZE)));
	const pagedPages = $derived(
		filteredPages.slice((fbPage - 1) * DIRECTORY_PAGE_SIZE, fbPage * DIRECTORY_PAGE_SIZE)
	);

	/** Mock pagination copy: one span, `1–N de N · Página X de Y`. */
	function rangeLabel(total: number, page: number, pages: number): string {
		if (total === 0) return '';
		const start = (page - 1) * DIRECTORY_PAGE_SIZE + 1;
		const end = Math.min(page * DIRECTORY_PAGE_SIZE, total);
		return `${start}–${end} de ${total} · Página ${page} de ${pages}`;
	}

	/* ------------------------------ RSS sources ------------------------------ */

	let rssDialog: HTMLDialogElement | undefined;
	let rssEditIndex: number | null = null;
	let rssUrl = $state('');
	let rssError = $state('');

	function openRssAdd(): void {
		rssEditIndex = null;
		rssUrl = '';
		rssError = '';
		rssDialog?.showModal();
	}

	function openRssEdit(index: number): void {
		rssEditIndex = index;
		rssUrl = draft.rss[index] ?? '';
		rssError = '';
		rssDialog?.showModal();
	}

	/** http(s) URL or a friendly message; returns the trimmed value. */
	function parseSourceUrl(raw: string, label: string): string {
		const value = raw.trim();
		if (value === '') throw new Error(`Completa la URL del ${label}.`);
		let parsed: URL;
		try {
			parsed = new URL(value);
		} catch {
			throw new Error(`La URL del ${label} no es válida.`);
		}
		if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
			throw new Error(`La URL del ${label} debe usar HTTP o HTTPS.`);
		}
		return value;
	}

	function submitRss(event: SubmitEvent): void {
		event.preventDefault();
		try {
			const url = parseSourceUrl(rssUrl, 'feed RSS');
			const next = [...draft.rss];
			if (rssEditIndex === null) next.push(url);
			else next[rssEditIndex] = url;
			draft.rss = next;
		} catch (cause) {
			rssError = cause instanceof Error ? cause.message : 'URL no válida.';
			return;
		}
		dirty = true;
		rssDialog?.close();
	}

	function removeRss(index: number): void {
		draft.rss.splice(index, 1);
		dirty = true;
	}

	/* --------------------------- Facebook sources ---------------------------- */

	let fbDialog: HTMLDialogElement | undefined;
	let fbEditIndex = $state<number | null>(null);
	let fbUrl = $state('');
	let fbLabel = $state('');
	let fbError = $state('');

	function openFbAdd(): void {
		fbEditIndex = null;
		fbUrl = '';
		fbLabel = '';
		fbError = '';
		fbDialog?.showModal();
	}

	function openFbEdit(index: number): void {
		fbEditIndex = index;
		fbUrl = draft.pages[index]?.url ?? '';
		fbLabel = draft.pages[index]?.label ?? '';
		fbError = '';
		fbDialog?.showModal();
	}

	function submitFb(event: SubmitEvent): void {
		event.preventDefault();
		const url = fbUrl.trim();
		const label = fbLabel.trim();
		if (url === '') {
			fbError = 'Completa la URL de la fuente de Facebook.';
			return;
		}
		if (normalizeFacebookPageRef(url) === null) {
			fbError = 'URL no válida: usa facebook.com/pagina, el id numérico o groups/123.';
			return;
		}
		const next = draft.pages.map((page) => ({ ...page }));
		if (fbEditIndex === null) next.push({ url, label });
		else next[fbEditIndex] = { url, label };
		draft.pages = next;
		dirty = true;
		fbDialog?.close();
	}

	function removeFb(index: number): void {
		draft.pages.splice(index, 1);
		dirty = true;
	}

	/**
	 * Serialized draft for the save action: one JSON field instead of
	 * per-row inputs, so pagination never drops unsaved rows.
	 */
	const facebookPayload = $derived(
		JSON.stringify(
			draft.pages
				.map((page) => ({
					page_id: normalizeFacebookPageRef(page.url) ?? '',
					label: page.label.trim()
				}))
				.filter((page) => page.page_id !== '')
		)
	);

	/**
	 * Keep the edited values in place (`reset: false`): the bound state
	 * already matches the saved row. `update()` still re-runs every load
	 * (invalidateAll) and publishes the action result as `form`.
	 */
	const handleSubmit: SubmitFunction = () => {
		submitting = true;
		return async ({ result, update }) => {
			try {
				await update({ reset: false });
			} finally {
				submitting = false;
			}
			if (result.type === 'success' && result.data?.action === 'save' && result.data.ok) {
				dirty = false;
			}
		};
	};

	/**
	 * X form: nothing to reset or prune — `reset: false` keeps the typed key
	 * visible and the stored-key note refreshes from the reloaded data.
	 */
	const handleXSubmit: SubmitFunction = () => {
		xSaving = true;
		return async ({ update }) => {
			try {
				await update({ reset: false });
			} finally {
				xSaving = false;
			}
		};
	};

	/** Typed X key mirror, so «Descartar cambios» clears it with the draft. */
	let xApiKey = $state('');
	/** Secret-field visibility toggles (mockup configSecretField pattern). */
	let xKeyVisible = $state(false);
	let aiKeyVisible = $state(false);

	/**
	 * Light-tasks fallback line (mockup configLLMStatus, adapted: our API has
	 * ONE shared service URL, so light tasks always use the main model's URL).
	 */
	const lightModelStatus = $derived.by(() => {
		const light = draft.ai_model_fast.trim();
		if (light !== '') {
			return `Tareas ligeras: ${light}. Utiliza la URL del servicio del modelo principal.`;
		}
		const main = draft.ai_model.trim();
		return `Tareas ligeras usará el modelo principal${main ? `: ${main}` : ', cuando lo configures'}, con su URL y su API key, si está indicada.`;
	});

	const providerChip = $derived(draft.ai_provider === 'openai' ? 'OpenAI API' : 'Modelo local');

	/** Savebar discard: back to the last loaded state, client-side only. */
	function discardChanges(): void {
		if (
			dirty &&
			!window.confirm(
				'¿Descartar los cambios pendientes? Se recuperará la última configuración cargada.'
			)
		) {
			return;
		}
		draft = toDraft(data.settings);
		xMode = data.settings.x_mode;
		xApiKey = '';
		dirty = false;
	}
</script>

<svelte:head>
	<title>Configuración | Media Monitor</title>
</svelte:head>

<header class="page-head">
	<h1 class="page-title">Configuración</h1>
</header>

<div class="config-workspace">
	<nav class="config-tabs" aria-label="Apartados de configuración">
		{#each TABS as tab (tab.id)}
			<button
				type="button"
				class={activeTab === tab.id ? 'active' : ''}
				aria-current={activeTab === tab.id ? 'page' : 'false'}
				onclick={() => selectTab(tab.id)}
			>
				{tab.label}
			</button>
		{/each}
	</nav>

	<p class="config-disclaimer">
		Los cambios se aplican al guardar: la ingesta, los cortes del resumen y la purga leen la
		configuración guardada en cada ciclo.
	</p>

	{#if form && ['save', 'save-x', 'create', 'toggle', 'delete'].includes(form.action ?? '')}
		<div class="config-feedback{form.ok ? '' : ' config-error'}" role={form.ok ? 'status' : 'alert'}>
			{form.message}
		</div>
	{/if}

	<div class="config-body">
		<!-- Keywords directory: own POST forms, so it lives outside the settings form. -->
		<section
			id="palabras-clave"
			class="config-rss-directory config-keyword-directory"
			hidden={activeTab !== 'keywords'}
			aria-labelledby="palabras-clave-title"
		>
			<header class="config-rss-directory-head">
				<div>
					<h2 id="palabras-clave-title">Palabras clave</h2>
					<p>Define los términos del monitoreo y su idioma.</p>
				</div>
			</header>
			<KeywordsPanel keywords={data.keywords} form={form} />
		</section>

		<form
			id="settings-save"
			method="POST"
			action="?/save"
			oninput={markDirty}
			onchange={markDirty}
			use:enhance={handleSubmit}
		>
			<!-- Hidden default submitter: Enter in any field saves instead of probing. -->
			<button type="submit" tabindex="-1" aria-label="Guardar" class="hidden"></button>

			<!-- Preserved settings without a v3 UI: hidden inputs keep the stored
				values traveling on every save (timezone is fixed by the contract,
				the caps/gdelt keep their server-side values). -->
			<input type="hidden" name="timezone" value={draft.timezone} />
			<input type="hidden" name="enrich_max_per_cycle" value={draft.enrich_max} />
			<input type="hidden" name="fetch_max_per_cycle" value={draft.fetch_max} />
			<input type="hidden" name="gdelt_enabled" value={draft.gdelt_enabled ? '1' : '0'} />
			<input type="hidden" name="rss_feeds" value={draft.rss.join('\n')} />
			<input type="hidden" name="facebook_pages" value={facebookPayload} />

			<!-- Operación -->
			<section
				id="operacion"
				class="panel config-section-card"
				hidden={activeTab !== 'operacion'}
				aria-labelledby="operacion-title"
			>
				<div class="panel-head">
					<h2 id="operacion-title">Operación del monitoreo</h2>
				</div>
				<div class="config-form-grid">
					<div>
						<label for="set-retention" class={LABEL_CLS}>Días de retención</label>
						<input
							id="set-retention"
							name="retention_days"
							type="number"
							min={0}
							step={1}
							bind:value={draft.retention_days}
							class={INPUT_CLS}
						/>
						<p class="field-hint">0 desactiva la purga automática.</p>
					</div>
					<div>
						<label for="set-focus-person" class={LABEL_CLS}>
							Persona principal bajo seguimiento
						</label>
						<select
							id="set-focus-person"
							name="digest_focus_person_id"
							bind:value={draft.focus_person_id}
							onchange={markDirty}
							disabled={submitting}
							class={INPUT_CLS}
							aria-describedby="set-focus-person-hint"
						>
							<option value="">Sin persona principal</option>
							{#if draft.focus_person_id && !data.persons.some((person) => String(person.id) === draft.focus_person_id)}
								<option value={draft.focus_person_id}>
									Persona configurada no disponible en la lista
								</option>
							{/if}
							{#each data.persons as person (person.id)}
								<option value={String(person.id)}>
									{person.name}{person.role ? ` · ${person.role}` : ''}{person.org ? ` · ${person.org}` : ''}
								</option>
							{/each}
						</select>
						<p id="set-focus-person-hint" class="field-hint">
							Define a quién se da seguimiento. Las palabras clave amplían la búsqueda; esta persona
							no tiene que aparecer en todas las noticias.
						</p>
					</div>
				</div>
				<!-- F7 vigilancia has no settings UI (mock operation = retention
				     + schedules only); the stored list round-trips untouched. -->
				{#each data.settings.watchlist as watchedId (watchedId)}
					<input type="hidden" name="watchlist" value={watchedId} />
				{/each}
				<h3 id="schedule-title">Horarios del resumen diario</h3>
				<p id="schedule-hint">Todos los días · Hora de Ciudad de México · Entre 1 y 8 horarios.</p>
				<div
					class="config-times"
					role="group"
					aria-labelledby="schedule-title"
					aria-describedby="schedule-hint"
				>
					{#each draft.digest_hours as hour, index (index)}
						<div>
							<label for={`schedule-hour-${index}`}>
								Resumen {index + 1}
								<!-- digest_hours stores whole hours (0-23), so the mock's
								     free time input stays a select here. -->
								<select
									id={`schedule-hour-${index}`}
									name="digest_hour"
									value={hour}
									onchange={(e) => setDigestHour(index, e.currentTarget.value)}
									disabled={submitting}
									class={INPUT_CLS}
								>
									{#each Array.from({ length: 24 }, (_, h) => h) as h (h)}
										<option value={h}>{String(h).padStart(2, '0')}:00</option>
									{/each}
								</select>
							</label>
							<button
								type="button"
								class="text-link"
								aria-label={`Eliminar el resumen ${index + 1}`}
								onclick={() => removeDigestHour(index)}
								disabled={submitting || draft.digest_hours.length <= 1}
							>
								Eliminar
							</button>
						</div>
					{/each}
				</div>
				<button
					type="button"
					class="button"
					onclick={addDigestHour}
					disabled={submitting || draft.digest_hours.length >= MAX_DIGEST_HOURS}
				>
					Añadir horario
				</button>
			</section>

			<!-- Fuentes -->
			<section
				id="fuentes"
				class="config-section-flat"
				hidden={activeTab !== 'fuentes'}
				aria-label="Fuentes"
			>
				<nav class="config-source-nav" aria-label="Tipos de fuentes">
					{#each SOURCE_TABS as [tab, label] (tab)}
						<button
							type="button"
							aria-current={sourceTab === tab ? 'page' : 'false'}
							onclick={() => selectSourceTab(tab)}
						>
							{label}
						</button>
					{/each}
				</nav>
				{#if sourceTab === 'social'}
					<nav class="config-source-nav config-social-nav" aria-label="Tipos de redes sociales">
						{#each SOCIAL_TABS as [tab, label] (tab)}
							<button
								type="button"
								aria-current={socialTab === tab ? 'page' : 'false'}
								onclick={() => selectSocialTab(tab)}
							>
								{label}
							</button>
						{/each}
					</nav>
				{/if}

				{#if directoryType}
					{@const meta = DIRECTORY_META[directoryType]}
					<section class="config-rss-directory" aria-labelledby="config-source-heading">
						<header class="config-rss-directory-head">
							<div>
								<h2 id="config-source-heading">{meta.title}</h2>
								<p>{meta.copy}</p>
							</div>
							<div class="config-rss-directory-tools">
								<div class="config-rss-search-box">
									<input
										type="search"
										aria-label={`Buscar en ${meta.title} por nombre o URL`}
										placeholder="Buscar por nombre o URL"
										autocomplete="off"
										bind:value={sourceQuery}
										oninput={resetDirectoryPages}
									/>
									<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
										<path d={ICON_PATHS.search} />
									</svg>
								</div>
								<!-- Scrapers stay out: the server registry is fixed, nothing to add. -->
								{#if directoryType === 'rss'}
									<button
										type="button"
										class="button"
										data-config-source-add
										onclick={openRssAdd}
										disabled={submitting}
									>
										{meta.add}
									</button>
								{:else if directoryType === 'facebook'}
									<button
										type="button"
										class="button"
										data-config-source-add
										onclick={openFbAdd}
										disabled={submitting}
									>
										{meta.add}
									</button>
								{/if}
							</div>
						</header>
						<!-- tabindex makes the scrollable frame keyboard-reachable (mockup pattern). -->
						<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
						<div
							class="config-rss-table-frame"
							role="region"
							aria-label="Listado de fuentes"
							tabindex="0"
						>
							<table class="config-rss-table" aria-label={meta.tableLabel}>
								<thead>
									<tr>
										<th scope="col">Nombre</th>
										<th scope="col">{meta.urlCol}</th>
										<th scope="col">Acciones</th>
									</tr>
								</thead>
								<tbody>
									{#if directoryType === 'rss'}
										{#each pagedRss as entry (entry.index)}
											<tr>
												<th scope="row">{rssName(entry.url)}</th>
												<td class="config-rss-url">{entry.url}</td>
												<td>
													<div class="config-rss-actions">
														<button
															type="button"
															class="button"
															onclick={() => openRssEdit(entry.index)}
															disabled={submitting}
														>
															Editar
														</button>
														<button
															type="button"
															class="text-link"
															aria-label={`Quitar el feed ${entry.url}`}
															onclick={() => removeRss(entry.index)}
															disabled={submitting}
														>
															Eliminar
														</button>
													</div>
												</td>
											</tr>
										{:else}
											<tr>
												<td colspan={3} class="config-rss-empty">
													{sourceQuery.trim() === ''
														? 'Aún no hay fuentes RSS. Añade la primera fuente para crear una fila.'
														: 'No hay fuentes que coincidan con la búsqueda.'}
												</td>
											</tr>
										{/each}
									{:else if directoryType === 'scraper'}
										{#each pagedScrapers as scraper (scraper.name)}
											<tr>
												<th scope="row">{scraper.name}</th>
												<td class="config-rss-url">
													<a href={scraper.base_url} target="_blank" rel="noreferrer">
														{scraper.base_url}
													</a>
												</td>
												<td>
													<!-- Fixed registry: enabling IS the row action. -->
													<label class="config-scraper-toggle">
														<input
															type="checkbox"
															name="scrapers"
															value={scraper.name}
															checked={draft.scrapers.includes(scraper.name)}
															onchange={(e) => toggleScraper(scraper.name, e.currentTarget.checked)}
															class={CHECK_CLS}
														/>
														<span>Activada</span>
													</label>
												</td>
											</tr>
										{:else}
											<tr>
												<td colspan={3} class="config-rss-empty">
													{availableScrapers.length === 0
														? 'No hay scrapers disponibles en el registro del servidor.'
														: 'No hay fuentes que coincidan con la búsqueda.'}
												</td>
											</tr>
										{/each}
									{:else if directoryType === 'facebook'}
										{#each pagedPages as entry (entry.index)}
											<tr>
												<th scope="row">{entry.page.label || 'Sin etiqueta'}</th>
												<td class="config-rss-url">{entry.page.url}</td>
												<td>
													<div class="config-rss-actions">
														<button
															type="button"
															class="button"
															onclick={() => openFbEdit(entry.index)}
															disabled={submitting}
														>
															Editar
														</button>
														<button
															type="button"
															class="text-link"
															aria-label={`Eliminar la fuente ${entry.page.label || entry.page.url}`}
															onclick={() => removeFb(entry.index)}
															disabled={submitting}
														>
															Eliminar
														</button>
													</div>
												</td>
											</tr>
										{:else}
											<tr>
												<td colspan={3} class="config-rss-empty">
													{sourceQuery.trim() === ''
														? 'Aún no hay páginas. Añade la primera página para crear una fila.'
														: 'No hay fuentes que coincidan con la búsqueda.'}
												</td>
											</tr>
										{/each}
									{/if}
								</tbody>
							</table>
						</div>
						{#if directoryType === 'rss' && filteredRss.length > 0}
							<div class="config-pagination">
								<span role="status">{rangeLabel(filteredRss.length, Math.min(rssPage, rssPageCount), rssPageCount)}</span>
								{#if rssPageCount > 1}
									<div>
										<button
											type="button"
											class="button"
											onclick={() => (rssPage = Math.max(1, rssPage - 1))}
											disabled={rssPage <= 1}
										>
											Anterior
										</button>
										<button
											type="button"
											class="button"
											onclick={() => (rssPage = Math.min(rssPageCount, rssPage + 1))}
											disabled={rssPage >= rssPageCount}
										>
											Siguiente
										</button>
									</div>
								{/if}
							</div>
						{:else if directoryType === 'scraper' && filteredScrapers.length > 0}
							<div class="config-pagination">
								<span role="status">{rangeLabel(filteredScrapers.length, Math.min(scraperPage, scraperPageCount), scraperPageCount)}</span>
								{#if scraperPageCount > 1}
									<div>
										<button
											type="button"
											class="button"
											onclick={() => (scraperPage = Math.max(1, scraperPage - 1))}
											disabled={scraperPage <= 1}
										>
											Anterior
										</button>
										<button
											type="button"
											class="button"
											onclick={() => (scraperPage = Math.min(scraperPageCount, scraperPage + 1))}
											disabled={scraperPage >= scraperPageCount}
										>
											Siguiente
										</button>
									</div>
								{/if}
							</div>
						{:else if directoryType === 'facebook' && filteredPages.length > 0}
							<div class="config-pagination">
								<span role="status">{rangeLabel(filteredPages.length, Math.min(fbPage, fbPageCount), fbPageCount)}</span>
								{#if fbPageCount > 1}
									<div>
										<button
											type="button"
											class="button"
											onclick={() => (fbPage = Math.max(1, fbPage - 1))}
											disabled={fbPage <= 1}
										>
											Anterior
										</button>
										<button
											type="button"
											class="button"
											onclick={() => (fbPage = Math.min(fbPageCount, fbPage + 1))}
											disabled={fbPage >= fbPageCount}
										>
											Siguiente
										</button>
									</div>
								{/if}
							</div>
						{/if}
					</section>
				{:else if socialTab === 'twitter'}
					<!-- Mock chip here reads «Sin conexión» (no backend in the mock);
					     our X source is backed by a real mode+key API, so no chip. -->
					<section
						class="panel config-section-card config-social-directory"
						aria-labelledby="x-title"
					>
						<div class="panel-head config-section-head">
							<h2 id="x-title">Twitter / X</h2>
						</div>
						<p>Configura el modo de acceso para esta red social.</p>
						<fieldset class="config-source-mode">
							<legend>Modo de la fuente</legend>
							<div class="config-source-mode-options">
								<label class="config-source-mode-option">
									<input
										form="x-save-form"
										type="radio"
										name="x_mode"
										value="free"
										checked={xMode === 'free'}
										onchange={() => (xMode = 'free')}
									/>
									<span>Gratuito</span>
								</label>
								<label class="config-source-mode-option">
									<input
										form="x-save-form"
										type="radio"
										name="x_mode"
										value="paid"
										checked={xMode === 'paid'}
										onchange={() => (xMode = 'paid')}
									/>
									<span>API de pago</span>
								</label>
							</div>
						</fieldset>
						{#if xMode === 'paid'}
							<div class="config-form-grid">
								<div class="config-secret-field">
									<label for="x-api-key">API key</label>
									<div class="config-secret-control">
										<input
											id="x-api-key"
											form="x-save-form"
											name="x_api_key"
											bind:value={xApiKey}
											type={xKeyVisible ? 'text' : 'password'}
											placeholder="Dejar vacío para conservar la actual"
											autocomplete="off"
										/>
										<button
											type="button"
											class="button"
											onclick={() => (xKeyVisible = !xKeyVisible)}
											aria-pressed={xKeyVisible}
											aria-controls="x-api-key"
										>
											{xKeyVisible ? 'Ocultar' : 'Mostrar'}
										</button>
									</div>
									<span>
										{#if data.settings.x_api_key_set}
											API key guardada.
										{:else}
											Sin key: se usará el modo gratuito como respaldo.
										{/if}
									</span>
								</div>
							</div>
						{/if}
						{#if xMode === 'free'}
							<p>
								Modo gratuito: las menciones de X provienen del índice de Google News
								(site:x.com). Limitaciones: sin autor de la cuenta; cobertura parcial —solo
								lo que Google indexa (medios y cuentas institucionales, no toda la
								conversación)—; la publicación puede tardar horas en reflejarse.
							</p>
						{/if}
						<button
							form="x-save-form"
							type="submit"
							class="button primary"
							disabled={xSaving}
						>
							Guardar X
						</button>
					</section>
				{:else}
					{@const plannedTitle = socialTab === 'tiktok' ? 'TikTok' : 'Instagram'}
					<section
						class="panel config-section-card config-social-directory"
						aria-labelledby={`${socialTab}-title`}
					>
						<div class="panel-head config-section-head">
							<h2 id={`${socialTab}-title`}>{plannedTitle}</h2>
							<span class="config-chip">En desarrollo</span>
						</div>
						<p>
							La integración con {plannedTitle} aún no está disponible. Aquí podrás administrar
							sus fuentes cuando esté habilitada.
						</p>
					</section>
				{/if}
			</section>

			<!-- LLM -->
			<section
				id="llm"
				class="panel config-section-card"
				hidden={activeTab !== 'llm'}
				aria-labelledby="llm-title"
			>
				<div class="panel-head config-section-head">
					<h2 id="llm-title">Modelo de lenguaje</h2>
					<span class="config-chip">{providerChip}</span>
				</div>
				<p>Un modelo principal y, opcionalmente, otro para tareas ligeras.</p>
				<fieldset class="config-source-mode">
					<legend>Proveedor</legend>
					<div class="config-source-mode-options">
						<label class="config-source-mode-option">
							<input
								type="radio"
								name="ai_provider"
								value="local"
								checked={draft.ai_provider === 'local'}
								onchange={() => (draft.ai_provider = 'local')}
							/>
							<span>Modelo local</span>
						</label>
						<label class="config-source-mode-option">
							<input
								type="radio"
								name="ai_provider"
								value="openai"
								checked={draft.ai_provider === 'openai'}
								onchange={() => (draft.ai_provider = 'openai')}
							/>
							<span>OpenAI (API)</span>
						</label>
					</div>
				</fieldset>
				<div class="config-model-block">
					<h3>Propósito general</h3>
					<p>Modelo principal para consultas, análisis y síntesis.</p>
					<div class="config-form-grid">
						<div>
							<label for="set-ai-base-url" class={LABEL_CLS}>URL del servicio</label>
							<input
								id="set-ai-base-url"
								name="ai_base_url"
								type="text"
								bind:value={draft.ai_base_url}
								placeholder={draft.ai_provider === 'local'
									? 'http://localhost:11434'
									: 'https://api.openai.com/v1'}
								class={INPUT_CLS}
							/>
						</div>
						<div>
							<label for="set-ai-model" class={LABEL_CLS}>Identificador del modelo</label>
							<input
								id="set-ai-model"
								name="ai_model"
								type="text"
								bind:value={draft.ai_model}
								placeholder="Identificador del modelo principal"
								class={INPUT_CLS}
							/>
						</div>
						{#if draft.ai_provider === 'openai'}
							<div class="config-secret-field">
								<label for="set-ai-key">API key (opcional)</label>
								<div class="config-secret-control">
									<input
										id="set-ai-key"
										name="ai_api_key"
										type={aiKeyVisible ? 'text' : 'password'}
										bind:value={draft.ai_api_key}
										autocomplete="off"
									/>
									<button
										type="button"
										class="button"
										onclick={() => (aiKeyVisible = !aiKeyVisible)}
										aria-pressed={aiKeyVisible}
										aria-controls="set-ai-key"
									>
										{aiKeyVisible ? 'Ocultar' : 'Mostrar'}
									</button>
								</div>
								<span>
									Se guarda en la base del cliente; el backend la usa para enriquecimiento,
									resumen y consultas.
								</span>
							</div>
						{/if}
					</div>
				</div>
				<div class="config-model-block">
					<div class="config-section-head">
						<h3>Tareas ligeras</h3>
						<span class="config-chip">Opcional</span>
					</div>
					<!-- Our API exposes ONE service URL (ai_base_url) shared by both
					     models; the mock's dedicated light-tasks URL does not exist
					     here and is deliberately not invented. -->
					<div class="config-form-grid">
						<div>
							<label for="set-ai-model-fast" class={LABEL_CLS}>Identificador del modelo</label>
							<input
								id="set-ai-model-fast"
								name="ai_model_fast"
								type="text"
								bind:value={draft.ai_model_fast}
								placeholder="Vacío: usar el modelo principal"
								class={INPUT_CLS}
							/>
						</div>
					</div>
					<p class="config-model-status" role="status">{lightModelStatus}</p>
				</div>
				<p>
					Solo se guardan la URL y los identificadores. La API key se guarda en la base del
					cliente; el backend la usa para enriquecimiento, resumen y consultas.
				</p>
				<div class="config-probe">
					<button type="submit" formaction="?/test-ai" disabled={submitting} class="button">
						Probar conexión
					</button>
					{#if form?.action === 'test-ai'}
						{#if form.ok}
							<p class="probe-ok">
								Conexión correcta
								{#if form.model}&middot; {form.model}{/if}
								{#if form.latency_ms !== null}&middot; {form.latency_ms} ms{/if}
							</p>
							{#if form.narrative}
								{#if form.narrative.ok && form.narrative.json_schema === 'supported'}
									<p class="probe-ok">
										Narrativa del digest: schema guiado OK
										{#if form.narrative.latency_ms !== null}&middot; {form.narrative.latency_ms} ms{/if}
									</p>
								{:else if form.narrative.ok}
									<p class="probe-warn">
										Narrativa del digest: sin json_schema; se regenera sin guía
									</p>
								{:else}
									<p class="probe-error">
										Narrativa del digest: error{form.narrative.error ? ` — ${form.narrative.error}` : ''}
									</p>
								{/if}
							{/if}
						{:else}
							<p class="probe-error">Error: {form.message}</p>
						{/if}
					{/if}
				</div>
			</section>
		</form>
	</div>

	<footer class="config-savebar">
		<span>{dirty ? 'Cambios pendientes de guardar' : 'Sin cambios pendientes'}</span>
		<div>
			<button type="button" class="button" onclick={discardChanges} disabled={submitting}>
				Descartar cambios
			</button>
			<button type="submit" form="settings-save" class="button primary" disabled={submitting}>
				Guardar configuración
			</button>
		</div>
	</footer>
</div>

<!-- Source dialogs live at page level: a <dialog> containing a <form>
	cannot nest inside the main save form (node_invalid_placement); the
	bind:this handles above keep them wired to their sections. -->
<dialog
	class="settings-dialog"
	bind:this={rssDialog}
	aria-labelledby="rss-dialog-title"
	closedby="any"
>
	<form onsubmit={submitRss}>
		<h5 id="rss-dialog-title">Agregar fuente</h5>
		<p>El cambio se aplicará a la lista. Después, guarda la configuración.</p>
		<label class="field-label" for="rss-url-input">URL del feed</label>
		<input
			id="rss-url-input"
			type="url"
			inputmode="url"
			placeholder="https://ejemplo.org/feed.xml"
			required
			bind:value={rssUrl}
			class={INPUT_CLS}
		/>
		<p class="field-hint" role="alert">{rssError}</p>
		<div class="dialog-actions">
			<button
				type="button"
				onclick={() => rssDialog?.close()}
				class={`${SMALL_BTN_CLS} border-line`}
			>
				Cancelar
			</button>
			<button type="submit" class={BTN_PRIMARY_CLS}>Aplicar cambios</button>
		</div>
	</form>
</dialog>

<dialog
	class="settings-dialog"
	bind:this={fbDialog}
	aria-labelledby="fb-dialog-title"
	closedby="any"
>
	<form onsubmit={submitFb}>
		<h5 id="fb-dialog-title">
			{fbEditIndex === null
				? 'Agregar fuente de Facebook'
				: 'Editar fuente de Facebook'}
		</h5>
		<p>La fuente se aplicará a la lista; después guarda la configuración.</p>
		<label class="field-label" for="fb-dialog-url">URL</label>
		<input
			id="fb-dialog-url"
			type="text"
			inputmode="url"
			placeholder="https://facebook.com/pagina"
			required
			bind:value={fbUrl}
			class={INPUT_CLS}
		/>
		<label class="field-label" for="fb-dialog-label">Etiqueta</label>
		<input
			id="fb-dialog-label"
			type="text"
			placeholder="Nombre para identificar la fuente"
			bind:value={fbLabel}
			class={INPUT_CLS}
		/>
		<p class="field-hint" role="alert">{fbError}</p>
		<div class="dialog-actions">
			<button
				type="button"
				onclick={() => fbDialog?.close()}
				class={`${SMALL_BTN_CLS} border-line`}
			>
				Cancelar
			</button>
			<button type="submit" class={BTN_PRIMARY_CLS}>Aplicar cambios</button>
		</div>
	</form>
</dialog>

<!-- X (Twitter): the UI card lives inside the Fuentes tab above, but the
	HTML form owner sits here at page level (a form cannot nest inside the
	main save form); its inputs associate via the form="x-save-form"
	attribute. Same ?/save-x action and handler as before. -->
<form id="x-save-form" method="POST" action="?/save-x" use:enhance={handleXSubmit}></form>
