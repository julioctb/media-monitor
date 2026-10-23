<script lang="ts">
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

	const TIMEZONES = ['America/Mexico_City', 'America/Monterrey', 'America/Tijuana', 'UTC'];

	/** Upper bound of daily digest cuts; mirrors the backend validator. */
	const MAX_DIGEST_HOURS = 8;

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
		gdelt_enabled: boolean;
		pages: PageDraft[];
		/** One RSS URL per line, exactly as edited in the textarea. */
		rss: string;
		/** Enabled scraper names (subset of data.scrapersAvailable). */
		scrapers: string[];
		ai_provider: 'local' | 'openai';
		ai_base_url: string;
		ai_model: string;
		ai_api_key: string;
	}

	function toDraft(settings: ClientSettings): SettingsDraft {
		return {
			timezone: settings.timezone,
			retention_days: String(settings.retention_days),
			digest_hours: [...settings.digest_hours],
			gdelt_enabled: settings.gdelt_enabled,
			pages: settings.facebook_pages.map((page) => ({
				url: `facebook.com/${page.page_id}`,
				label: page.label
			})),
			rss: settings.rss_feeds.join('\n'),
			scrapers: [...settings.scrapers],
			ai_provider: settings.ai_provider,
			ai_base_url: settings.ai_base_url ?? '',
			ai_model: settings.ai_model ?? '',
			ai_api_key: settings.ai_api_key ?? ''
		};
	}

	// Intentional snapshot: the draft starts from the loaded row and is then
	// edited in place; later `data` updates must not clobber the form.
	// svelte-ignore state_referenced_locally
	let draft = $state<SettingsDraft>(toDraft(data.settings));
	let dirty = $state(false);
	let submitting = $state(false);
	/** Inline per-row URL hints appear once a save persisted (or dropped) rows. */
	let showRowHints = $state(false);

	// X mode snapshot: like `draft`, a local edit surface published by its own
	// save; `data` refreshes must not revert an unsaved selection.
	// svelte-ignore state_referenced_locally
	let xMode: XMode = $state(data.settings.x_mode);
	/** Gates the X section's submit while its request is in flight. */
	let xSaving = $state(false);

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

	function addPage(): void {
		draft.pages.push({ url: '', label: '' });
		dirty = true;
	}

	function removePage(index: number): void {
		draft.pages.splice(index, 1);
		dirty = true;
	}

	/** Unparseable non-empty URL: the server would drop this row on save. */
	function rowInvalid(url: string): boolean {
		return url.trim() !== '' && normalizeFacebookPageRef(url) === null;
	}

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
			if (result.type === 'success') {
				const payload = result.data;
				if (payload?.action === 'save' && payload.ok) {
					// Mirror the server: blank rows never persist; invalid ones stay
					// flagged by the inline hint until fixed or removed.
					draft.pages = draft.pages.filter(
						(page) => page.url.trim() !== '' || page.label.trim() !== ''
					);
					showRowHints = true;
					dirty = false;
				}
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

<div class="settings-layout">
	<nav class="section-nav" aria-label="Secciones de configuración">
		<a href="#palabras-clave">Palabras clave</a>
		<a href="#operacion">Operación</a>
		<a href="#fuentes">Fuentes</a>
		<a href="#llm">LLM</a>
	</nav>

	<div class="settings-flow">
		<!-- Keywords panel: own POST forms, so it lives outside the settings form. -->
		<section id="palabras-clave" class="panel" aria-labelledby="palabras-clave-title">
			<div class="panel-head">
				<h2 id="palabras-clave-title">Palabras clave</h2>
				<p class="panel-note">Términos que activan el monitoreo, asociados a su idioma.</p>
			</div>
			<KeywordsPanel keywords={data.keywords} form={form} />
		</section>

		<form
			method="POST"
			action="?/save"
			class="settings-flow"
			oninput={markDirty}
			onchange={markDirty}
			use:enhance={handleSubmit}
		>
			<!-- Hidden default submitter: Enter in any field saves instead of probing. -->
			<button type="submit" tabindex="-1" aria-label="Guardar" class="hidden"></button>

			<!-- Operación -->
			<section id="operacion" class="panel" aria-labelledby="operacion-title">
				<div class="panel-head">
					<h2 id="operacion-title">Operación</h2>
					<p class="panel-note">Ajustes generales de tiempo y conservación de datos.</p>
				</div>
				<div class="field-grid">
					<div>
						<label for="set-timezone" class={LABEL_CLS}>Zona horaria</label>
						<input
							id="set-timezone"
							name="timezone"
							type="text"
							list="timezone-options"
							bind:value={draft.timezone}
							class={INPUT_CLS}
						/>
						<datalist id="timezone-options">
							{#each TIMEZONES as tz (tz)}
								<option value={tz}></option>
							{/each}
						</datalist>
						<p class="field-hint">Identificador IANA, por ejemplo, America/Mexico_City.</p>
					</div>
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
					<div class="sm:col-span-2 lg:col-span-3">
						<span class={LABEL_CLS} id="digest-hours-label">Horarios del resumen diario</span>
						<div
							class="mt-1 flex flex-wrap items-center gap-2"
							role="group"
							aria-labelledby="digest-hours-label"
						>
							{#each draft.digest_hours as hour, index (index)}
								<span class="digest-hour-chip">
									<input
										aria-label={`Hora del corte ${index + 1}`}
										aria-describedby="digest-hours-hint"
										name="digest_hour"
										type="number"
										min={0}
										max={23}
										step={1}
										value={hour}
										oninput={(e) => setDigestHour(index, e.currentTarget.value)}
										disabled={submitting}
										class="digest-hour-input"
									/>
									<button
										type="button"
										aria-label={`Quitar el corte de las ${hour}:00`}
										onclick={() => removeDigestHour(index)}
										disabled={submitting || draft.digest_hours.length <= 1}
										class="text-muted transition-colors hover:text-danger disabled:opacity-40"
									>
										×
									</button>
								</span>
							{/each}
							<button
								type="button"
								onclick={addDigestHour}
								disabled={submitting || draft.digest_hours.length >= MAX_DIGEST_HOURS}
								class={PROBE_BTN_CLS}
							>
								+ Agregar hora
							</button>
						</div>
						<p class="field-hint" id="digest-hours-hint">
							Entre 1 y 8 cortes diarios (0&ndash;23). El resumen se regenera en cada corte.
						</p>
					</div>
				</div>
			</section>

			<!-- Fuentes -->
			<section id="fuentes" class="panel" aria-labelledby="fuentes-title">
				<div class="panel-head">
					<h2 id="fuentes-title">Fuentes</h2>
					<p class="panel-note">Define los orígenes que alimentarán el monitoreo.</p>
				</div>
				<div class="source-grid">
					<article class="source-card">
						<h3>Feed RSS</h3>
						<p>Direcciones de noticias, una URL por línea.</p>
						<textarea
							aria-label="Direcciones RSS"
							name="rss_feeds"
							rows="4"
							bind:value={draft.rss}
							placeholder={'https://ejemplo.com/feed.xml\nhttps://otrositio.com/rss'}
							class={`w-full ${INPUT_CLS} font-mono text-xs`}
						></textarea>
						<label class="check-row mt-2">
							<input
								type="checkbox"
								name="gdelt_enabled"
								value="1"
								bind:checked={draft.gdelt_enabled}
								class={CHECK_CLS}
							/>
							Incluir GDELT
						</label>
					</article>

					<article class="source-card">
						<h3>Scrapers</h3>
						<p>Medios sin RSS: el worker revisa su portada en cada ciclo.</p>
						{#if availableScrapers.length === 0}
							<p class="field-hint">No hay scrapers disponibles en el registro del servidor.</p>
						{:else}
							<div class="grid gap-2">
								{#each availableScrapers as scraper (scraper.name)}
									<label class="check-row">
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
							</div>
						{/if}
					</article>

					<article class="source-card source-card--wide">
						<h3>Redes sociales</h3>
						<p>Páginas o grupos públicos de Facebook, por URL. Sin tokens: se lee el HTML público.</p>
						{#if draft.pages.length === 0}
							<p class="keywords-empty">Sin páginas: agrega la URL de la primera.</p>
						{:else}
							<div class="table-wrap">
								<table class="data-table">
									<thead>
										<tr>
											<th scope="col" class="w-[45%]">URL</th>
											<th scope="col" class="w-[35%]">Etiqueta</th>
											<th scope="col">Acciones</th>
										</tr>
									</thead>
									<tbody>
										{#each draft.pages as page, index (page)}
											<tr>
												<td data-label="URL">
													<input
														id={`fb-url-${index}`}
														name="fb_url"
														type="text"
														bind:value={page.url}
														placeholder="facebook.com/pagina"
														class={INPUT_CLS}
													/>
													{#if showRowHints && rowInvalid(page.url)}
														<p class="mt-1 text-xs text-danger">
															URL no válida: usa facebook.com/pagina, el id numérico o groups/123.
														</p>
													{/if}
												</td>
												<td data-label="Etiqueta">
													<input
														id={`fb-label-${index}`}
														name="fb_label"
														type="text"
														bind:value={page.label}
														placeholder="Opcional"
														class={INPUT_CLS}
													/>
												</td>
												<td data-label="Acciones">
													<button
														type="button"
														aria-label={`Quitar la fuente ${page.label || page.url || index + 1}`}
														onclick={() => removePage(index)}
														disabled={submitting}
														class="text-muted transition-colors hover:text-danger disabled:opacity-40"
													>
														×
													</button>
												</td>
											</tr>
										{/each}
									</tbody>
								</table>
							</div>
						{/if}
						<button
							type="button"
							onclick={addPage}
							disabled={submitting}
							class="mt-3 rounded-full border border-dashed border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-warm disabled:opacity-60"
						>
							+ Agregar fuente
						</button>
					</article>

					<article class="source-card source-card--wide">
						<h3>X (Twitter)</h3>
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
								<p
									class="mt-4 rounded-lg px-4 py-3 text-sm ring-1 ring-inset bg-surface-warm text-ink-2 ring-line"
								>
									Modo gratuito: las menciones de X provienen del índice de Google News (site:x.com).
									Limitaciones: sin autor de la cuenta; cobertura parcial —solo lo que Google indexa
									(medios y cuentas institucionales, no toda la conversación)—; la publicación puede
									tardar horas en reflejarse.
								</p>
							{/if}

							<div class="mt-4">
								<label for="x-api-key" class={LABEL_CLS}>API key</label>
								<input
									id="x-api-key"
									form="x-save-form"
									name="x_api_key"
									type="password"
									placeholder="Dejar vacío para conservar la actual"
									autocomplete="off"
									class={INPUT_CLS}
								/>
								{#if data.settings.x_api_key_set}
									<p class="field-hint">API key guardada</p>
								{:else if xMode === 'paid'}
									<p class="field-hint">Sin key: se usará el modo gratuito como respaldo</p>
								{/if}
							</div>

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
					</article>

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
			<section id="llm" class="panel" aria-labelledby="llm-title">
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
							{:else}
								<p class="mt-2 text-xs text-danger">Error: {form.message}</p>
							{/if}
						{/if}
					</div>
				</div>
			</section>

			<div class="footer-actions">
				<button
					type="submit"
					disabled={submitting}
					class="btn-primary inline-flex min-h-[44px] items-center justify-center rounded-full border border-accent bg-accent px-[22px] text-sm font-semibold text-accent-on transition-colors hover:border-accent-hover hover:bg-accent-hover active:border-accent-active active:bg-accent-active disabled:opacity-60"
				>
					Guardar configuración
					{#if dirty}
						<span
							class="ml-1.5 inline-block size-1.5 rounded-full bg-warn"
							title="Cambios sin guardar"
						></span>
						<span class="sr-only">(cambios sin guardar)</span>
					{/if}
				</button>
				<p class="storage-note">Los cambios se aplican al pulsar Guardar configuración.</p>
			</div>
		</form>

		<!-- X (Twitter): the UI card lives inside the Fuentes grid above, but the
			HTML form owner sits here at page level (a form cannot nest inside the
			main save form); its inputs associate via the form="x-save-form"
			attribute. Same ?/save-x action and handler as before. -->
		<form id="x-save-form" method="POST" action="?/save-x" use:enhance={handleXSubmit}></form>
	</div>
</div>
