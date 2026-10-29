<script lang="ts">
	import { onMount } from 'svelte';

	import { enhance } from '$app/forms';

	import KeywordsPanel from '$lib/components/KeywordsPanel.svelte';
	import { BTN_PRIMARY_CLS, INPUT_CLS } from '$lib/ui';
	import type { AvailableScraper, ClientSettings, XMode } from '$lib/api';
	import { normalizeFacebookPageRef } from '$lib/facebook-page';
	import type { PageProps, SubmitFunction } from './$types';

	let { data, form }: PageProps = $props();

	const LABEL_CLS = 'field-label';
	const CHECK_CLS = 'size-4 rounded border-line accent-accent';
	const PROBE_BTN_CLS =
		'inline-flex min-h-[36px] items-center justify-center rounded-full border border-line bg-white px-3 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-warm disabled:opacity-60';
	const SMALL_BTN_CLS =
		'inline-flex min-h-[36px] items-center justify-center rounded-full border border-line bg-white px-3 py-1.5 text-xs font-semibold text-ink-2 transition-colors hover:bg-surface-warm disabled:opacity-60';

	/** Upper bound of daily digest cuts; mirrors the backend validator. */
	const MAX_DIGEST_HOURS = 8;

	/** Facebook sources shown per page (maqueta v2 contract). */
	const FACEBOOK_PAGE_SIZE = 20;

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
	let fbQuery = $state('');
	let fbPage = $state(1);

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

	function applyFbFilter(event: SubmitEvent): void {
		event.preventDefault();
		fbPage = 1;
	}

	/** Draft rows matching the search, in draft order. */
	const filteredPages = $derived.by(() => {
		const query = fbQuery.trim().toLocaleLowerCase('es');
		if (query === '') return draft.pages.map((page, index) => ({ page, index }));
		return draft.pages
			.map((page, index) => ({ page, index }))
			.filter(({ page }) => `${page.label} ${page.url}`.toLocaleLowerCase('es').includes(query));
	});
	const fbPageCount = $derived(Math.max(1, Math.ceil(filteredPages.length / FACEBOOK_PAGE_SIZE)));
	const pagedPages = $derived.by(() => {
		const start = (fbPage - 1) * FACEBOOK_PAGE_SIZE;
		return filteredPages.slice(start, start + FACEBOOK_PAGE_SIZE);
	});
	const fbRangeLabel = $derived.by(() => {
		const total = filteredPages.length;
		if (total === 0) return 'Sin resultados';
		const start = (fbPage - 1) * FACEBOOK_PAGE_SIZE + 1;
		const end = Math.min(fbPage * FACEBOOK_PAGE_SIZE, total);
		return `Mostrando ${start}–${end} de ${total} ${total === 1 ? 'fuente' : 'fuentes'}`;
	});

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
	<p class="lead">
		Administra los términos de monitoreo, las fuentes y el procesamiento de la cobertura.
	</p>
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
		<div
			role={form.ok ? 'status' : 'alert'}
			class={`mt-4 rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${
				form.ok
					? 'bg-success/10 text-success ring-success/30'
					: 'bg-danger/10 text-danger ring-danger/30'
			}`}
		>
			{form.message}
		</div>
	{/if}

	<div class="config-body">
		<!-- Keywords panel: own POST forms, so it lives outside the settings form. -->
		<section
			id="palabras-clave"
			class="panel"
			hidden={activeTab !== 'keywords'}
			aria-labelledby="palabras-clave-title"
		>
			<div class="panel-head">
				<h2 id="palabras-clave-title">Palabras clave</h2>
				<p class="panel-note">
					Términos que activan el monitoreo, asociados a su idioma. Son independientes de la
					persona principal bajo seguimiento.
				</p>
			</div>
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

			<!-- Preserved settings without a v2 UI: hidden inputs keep the stored
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
				class="panel"
				hidden={activeTab !== 'operacion'}
				aria-labelledby="operacion-title"
			>
				<div class="panel-head">
					<h2 id="operacion-title">Operación del monitoreo</h2>
					<p class="panel-note">Ajustes generales de tiempo y conservación de datos.</p>
				</div>
				<div class="field-grid">
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
				<div class="schedule-block">
					<h3 id="schedule-title">Horarios del resumen diario</h3>
					<p class="field-hint" id="schedule-hint">
						Todos los días · formato de 24 horas. De 1 a 8 horarios.
					</p>
					<div
						class="schedule-line"
						role="group"
						aria-labelledby="schedule-title"
						aria-describedby="schedule-hint"
					>
						{#each draft.digest_hours as hour, index (index)}
							<div class="schedule-item">
								<label for={`schedule-hour-${index}`}>Resumen {index + 1}</label>
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
								<button
									type="button"
									aria-label={`Eliminar el resumen ${index + 1}`}
									onclick={() => removeDigestHour(index)}
									disabled={submitting || draft.digest_hours.length <= 1}
									class={SMALL_BTN_CLS}
								>
									Eliminar
								</button>
							</div>
						{/each}
						<button
							type="button"
							onclick={addDigestHour}
							disabled={submitting || draft.digest_hours.length >= MAX_DIGEST_HOURS}
							class={SMALL_BTN_CLS}
						>
							+ Añadir horario
						</button>
					</div>
					<p class="field-hint">Los horarios usan la hora de Ciudad de México.</p>
				</div>
			</section>

			<!-- Fuentes -->
			<section
				id="fuentes"
				class="panel"
				hidden={activeTab !== 'fuentes'}
				aria-labelledby="fuentes-title"
			>
				<div class="panel-head">
					<h2 id="fuentes-title">Fuentes</h2>
					<p class="panel-note">Define los orígenes que alimentarán el monitoreo.</p>
				</div>
				<div class="source-grid">
					<section class="source-card" aria-labelledby="rss-title">
						<div class="source-list-head">
							<div>
								<h3 id="rss-title">Feed RSS</h3>
								<p>Fuentes de noticias con feed RSS.</p>
							</div>
							<button type="button" onclick={openRssAdd} disabled={submitting} class={SMALL_BTN_CLS}>
								Agregar feed
							</button>
						</div>
						<div class="source-list" role="list" aria-label="Feeds RSS">
							{#each draft.rss as url, index (`${index}:${url}`)}
								<div class="source-item" role="listitem">
									<div class="source-item-main">
										<span class="source-item-url">{url}</span>
									</div>
									<div class="source-item-actions">
										<button
											type="button"
											onclick={() => openRssEdit(index)}
											disabled={submitting}
											class={SMALL_BTN_CLS}
										>
											Editar
										</button>
										<button
											type="button"
											aria-label={`Quitar el feed ${url}`}
											onclick={() => removeRss(index)}
											disabled={submitting}
											class={`${SMALL_BTN_CLS} btn-delete`}
										>
											Eliminar
										</button>
									</div>
								</div>
							{/each}
							{#if draft.rss.length === 0}
								<p class="source-empty">Sin feeds RSS registrados.</p>
							{/if}
						</div>
					</section>

					<section class="source-card" aria-labelledby="scraper-title">
						<div class="source-list-head">
							<div>
								<h3 id="scraper-title">Scrapers</h3>
								<p>Medios sin RSS: el worker revisa su portada en cada ciclo.</p>
							</div>
						</div>
						<div class="source-list">
							{#if availableScrapers.length === 0}
								<p class="source-empty">No hay scrapers disponibles en el registro del servidor.</p>
							{:else}
								{#each availableScrapers as scraper (scraper.name)}
									<label class="check-row source-check">
										<input
											type="checkbox"
											name="scrapers"
											value={scraper.name}
											checked={draft.scrapers.includes(scraper.name)}
											onchange={(e) => toggleScraper(scraper.name, e.currentTarget.checked)}
											class={CHECK_CLS}
										/>
										<span>{scraper.name}</span>
										<a
											href={scraper.base_url}
											target="_blank"
											rel="noreferrer"
											class="text-xs text-meta underline hover:text-ink-2"
										>
											{scraper.base_url}
										</a>
									</label>
								{/each}
							{/if}
						</div>
					</section>


					<div class="social-section">
						<h3>Redes sociales</h3>
						<p class="panel-note">Fuentes organizadas por plataforma.</p>
						<div class="social-stack">
							<section class="social-platform" aria-labelledby="facebook-title">
								<h4 id="facebook-title">Facebook</h4>
								<p>Páginas o grupos públicos registrados por URL y etiqueta.</p>
								<div class="facebook-toolbar">
									<p class="facebook-count">
										{draft.pages.length}
										{draft.pages.length === 1 ? 'fuente' : 'fuentes'}
									</p>
									<button
										type="button"
										onclick={openFbAdd}
										disabled={submitting}
										class={SMALL_BTN_CLS}
									>
										+ Agregar fuente
									</button>
								</div>
								<div class="facebook-search">
									<label class="field-label" for="facebook-search">Buscar fuente</label>
									<div class="facebook-search-controls">
										<input
											id="facebook-search"
											type="search"
											placeholder="Etiqueta o URL"
											autocomplete="off"
											bind:value={fbQuery}
											oninput={() => (fbPage = 1)}
											class={INPUT_CLS}
										/>
										<button type="button" onclick={() => (fbPage = 1)} class={SMALL_BTN_CLS}>
											Buscar
										</button>
									</div>
								</div>
								<div class="table-wrap">
									<table class="facebook-table" aria-label="Fuentes de Facebook">
										<thead>
											<tr>
												<th scope="col">Etiqueta</th>
												<th scope="col">URL</th>
												<th scope="col">Acciones</th>
											</tr>
										</thead>
										<tbody>
											{#each pagedPages as entry (entry.index)}
												<tr>
													<td data-label="Etiqueta">{entry.page.label || 'Sin etiqueta'}</td>
													<td data-label="URL">{entry.page.url}</td>
													<td data-label="Acciones">
														<button
															type="button"
															onclick={() => openFbEdit(entry.index)}
															disabled={submitting}
															class={SMALL_BTN_CLS}
														>
															Editar
														</button>
														<button
															type="button"
															aria-label={`Eliminar la fuente ${entry.page.label || entry.page.url}`}
															onclick={() => removeFb(entry.index)}
															disabled={submitting}
															class={`${SMALL_BTN_CLS} btn-delete`}
														>
															Eliminar
														</button>
													</td>
												</tr>
											{:else}
												<tr>
													<td colspan={3} class="empty-row">
														{fbQuery.trim() === ''
															? 'No hay fuentes de Facebook configuradas.'
															: 'No hay fuentes que coincidan con la búsqueda.'}
													</td>
												</tr>
											{/each}
										</tbody>
									</table>
								</div>
								<div class="facebook-pagination">
									<p role="status">{fbRangeLabel}</p>
									<div class="facebook-page-actions">
										<button
											type="button"
											onclick={() => (fbPage = Math.max(1, fbPage - 1))}
											disabled={fbPage <= 1}
											class={SMALL_BTN_CLS}
										>
											Anterior
										</button>
										<span>Página {fbPage} de {fbPageCount}</span>
										<button
											type="button"
											onclick={() => fbPage = Math.min(fbPageCount, fbPage + 1)}
											disabled={fbPage >= fbPageCount}
											class={SMALL_BTN_CLS}
										>
											Siguiente
										</button>
									</div>
								</div>

						</section>

							<section class="social-platform" aria-labelledby="x-title">
								<h4 id="x-title">X (Twitter)</h4>
								<p>Elige cómo se obtienen las menciones de X.</p>
								<span id="x-mode-label" class={LABEL_CLS}>Modo de la fuente</span>
								<div class="provider-radios" role="radiogroup" aria-labelledby="x-mode-label">
									<label class="radio-option">
										<input
											form="x-save-form"
											type="radio"
											name="x_mode"
											value="free"
											checked={xMode === 'free'}
											onchange={() => (xMode = 'free')}
										/>
										Gratuito
									</label>
									<label class="radio-option">
										<input
											form="x-save-form"
											type="radio"
											name="x_mode"
											value="paid"
											checked={xMode === 'paid'}
											onchange={() => (xMode = 'paid')}
										/>
										API de pago
									</label>
								</div>

								{#if xMode === 'free'}
									<div class="mt-4">
										<p class="x-mode-note">
											Modo gratuito: las menciones de X provienen del índice de Google News
											(site:x.com). Limitaciones: sin autor de la cuenta; cobertura parcial —solo
											lo que Google indexa (medios y cuentas institucionales, no toda la
											conversación)—; la publicación puede tardar horas en reflejarse.
										</p>
									</div>
								{/if}

								{#if xMode === 'paid'}
									<div class="x-api-field">
										<label for="x-api-key" class={LABEL_CLS}>API key</label>
										<input
											id="x-api-key"
											form="x-save-form"
											name="x_api_key"
											bind:value={xApiKey}
											type="password"
											placeholder="Dejar vacío para conservar la actual"
											autocomplete="off"
											class={INPUT_CLS}
										/>
										{#if data.settings.x_api_key_set}
											<p class="field-hint">API key guardada</p>
										{:else}
											<p class="field-hint">Sin key: se usará el modo gratuito como respaldo</p>
										{/if}
									</div>
								{/if}

								<div class="mt-4">
									<button
										form="x-save-form"
										type="submit"
										disabled={xSaving}
										class={BTN_PRIMARY_CLS}
									>
										Guardar X
									</button>
								</div>
							</section>

							<section class="social-platform social-platform--planned" aria-labelledby="tiktok-title">
								<span class="status-chip off">En desarrollo</span>
								<h4 id="tiktok-title">TikTok</h4>
								<p>La configuración de perfiles se habilitará cuando se integre esta fuente.</p>
							</section>

							<section
								class="social-platform social-platform--planned"
								aria-labelledby="instagram-title"
							>
								<span class="status-chip off">En desarrollo</span>
								<h4 id="instagram-title">Instagram</h4>
								<p>La configuración de perfiles se habilitará cuando se integre esta fuente.</p>
							</section>
						</div>
					</div>

					<article class="source-card wip">
						<span class="status-chip off">En desarrollo</span>
						<h3>Datos de campo</h3>
						<p>
							Formularios y encuestas de carga manual. La configuración se habilitará en una
							próxima etapa.
						</p>
					</article>
				</div>
			</section>

			<!-- LLM -->
			<section
				id="llm"
				class="panel"
				hidden={activeTab !== 'llm'}
				aria-labelledby="llm-title"
			>
				<div class="panel-head">
					<h2 id="llm-title">Modelo de lenguaje</h2>
					<p class="panel-note">Selecciona cómo se procesarán las consultas y el enriquecimiento.</p>
				</div>
				<span id="ai-provider-label" class={LABEL_CLS}>Proveedor</span>
				<div class="provider-radios" role="radiogroup" aria-labelledby="ai-provider-label">
					<label class="radio-option">
						<input
							type="radio"
							name="ai_provider"
							value="local"
							checked={draft.ai_provider === 'local'}
							onchange={() => (draft.ai_provider = 'local')}
						/>
						Modelo local
					</label>
					<label class="radio-option">
						<input
							type="radio"
							name="ai_provider"
							value="openai"
							checked={draft.ai_provider === 'openai'}
							onchange={() => (draft.ai_provider = 'openai')}
						/>
						OpenAI (API)
					</label>
				</div>

				<!-- The endpoint/model pair serves both providers; the panel stays
					visible so switching providers never wipes stored values. -->
				<div class="provider-panel mt-4">
					<div class="field-grid">
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
								placeholder="Nombre configurado en el servidor"
								class={INPUT_CLS}
							/>
						</div>
						<div>
							<label for="set-ai-model-fast" class={LABEL_CLS}
								>Modelo para tareas ligeras</label
							>
							<input
								id="set-ai-model-fast"
								name="ai_model_fast"
								type="text"
								bind:value={draft.ai_model_fast}
								placeholder="Vacío = usar el modelo principal"
								class={INPUT_CLS}
							/>
						</div>
					</div>
					{#if draft.ai_provider === 'openai'}
						<div class="mt-4">
							<label for="set-ai-key" class={LABEL_CLS}>API key</label>
							<input
								id="set-ai-key"
								name="ai_api_key"
								type="password"
								bind:value={draft.ai_api_key}
								autocomplete="off"
								class={INPUT_CLS}
							/>
							<p class="field-hint">
								Se guarda en la base del cliente; el backend la usa para enriquecimiento,
								resumen y consultas.
							</p>
						</div>
					{/if}
					<div class="mt-4">
						<button type="submit" formaction="?/test-ai" disabled={submitting} class={PROBE_BTN_CLS}>
							Probar conexión
						</button>
						{#if form?.action === 'test-ai'}
							{#if form.ok}
								<p class="mt-2 text-xs text-success">
									Conexión correcta
									{#if form.model}&middot; {form.model}{/if}
									{#if form.latency_ms !== null}&middot; {form.latency_ms} ms{/if}
								</p>
								{#if form.narrative}
									{#if form.narrative.ok && form.narrative.json_schema === 'supported'}
										<p class="mt-1 text-xs text-success">
											Narrativa del digest: schema guiado OK
											{#if form.narrative.latency_ms !== null}&middot; {form.narrative.latency_ms} ms{/if}
										</p>
									{:else if form.narrative.ok}
										<p class="mt-1 text-xs text-warning">
											Narrativa del digest: sin json_schema; se regenera sin guía
										</p>
									{:else}
										<p class="mt-1 text-xs text-danger">
											Narrativa del digest: error{form.narrative.error ? ` — ${form.narrative.error}` : ''}
										</p>
									{/if}
								{/if}
							{:else}
								<p class="mt-2 text-xs text-danger">Error: {form.message}</p>
							{/if}
						{/if}
					</div>
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


		<!-- X (Twitter): the UI card lives inside the Fuentes grid above, but the
			HTML form owner sits here at page level (a form cannot nest inside the
			main save form); its inputs associate via the form="x-save-form"
			attribute. Same ?/save-x action and handler as before. -->
		<form id="x-save-form" method="POST" action="?/save-x" use:enhance={handleXSubmit}></form>
