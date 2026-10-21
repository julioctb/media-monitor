<script lang="ts">
	import { enhance } from '$app/forms';

	import { INPUT_CLS } from '$lib/ui';
	import type { AvailableScraper, ClientSettings } from '$lib/api';
	import type { PageProps, SubmitFunction } from './$types';

	let { data, form }: PageProps = $props();

	const LABEL_CLS = 'field-label';
	const CHECK_CLS = 'size-4 rounded border-line accent-accent';
	const PROBE_BTN_CLS =
		'inline-flex min-h-[36px] items-center justify-center rounded-full border border-line bg-white px-3 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-surface-warm disabled:opacity-60';

	const TIMEZONES = ['America/Mexico_City', 'America/Monterrey', 'America/Tijuana', 'UTC'];

	/** Upper bound of daily digest cuts; mirrors the backend validator. */
	const MAX_DIGEST_HOURS = 8;

	// Keyword CRUD lives on /keywords; settings only renders global operation.

	interface PageDraft {
		page_id: string;
		token: string;
		label: string;
		/** Normalized on load: legacy rows without kind read as page. */
		kind: 'page' | 'group';
	}

	interface SettingsDraft {
		client_name: string;
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
			client_name: settings.client_name,
			timezone: settings.timezone,
			retention_days: String(settings.retention_days),
			digest_hours: [...settings.digest_hours],
			gdelt_enabled: settings.gdelt_enabled,
			pages: settings.facebook_pages.map((page) => ({ ...page, kind: page.kind ?? 'page' })),
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
		draft.pages.push({ page_id: '', token: '', label: '', kind: 'page' });
		dirty = true;
	}

	function removePage(index: number): void {
		draft.pages.splice(index, 1);
		dirty = true;
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
					dirty = false;
				}
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

{#if form?.action === 'save'}
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
		<a href="#operacion">Operación</a>
		<a href="#fuentes">Fuentes</a>
		<a href="#llm">LLM</a>
	</nav>

	<div class="settings-flow">
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
					<p class="panel-note">Ajustes generales de identidad, tiempo y conservación de datos.</p>
				</div>
				<div class="field-grid">
					<div>
						<label for="set-name" class={LABEL_CLS}>Nombre del cliente</label>
						<input
							id="set-name"
							name="client_name"
							type="text"
							maxlength={200}
							bind:value={draft.client_name}
							placeholder="Mi marca"
							class={INPUT_CLS}
						/>
					</div>
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

					<article class="source-card">
						<h3>Redes sociales</h3>
						<p>Páginas y grupos de Facebook con su id y token de acceso.</p>
						{#if draft.pages.length === 0}
							<p class="field-hint">Sin páginas ni grupos: agrega uno con su id y token de lectura.</p>
						{/if}
						<div class="grid gap-3">
							{#each draft.pages as page, index (page)}
								<div class="rounded-xl border border-line-soft bg-white p-3">
									<div class="grid gap-3 sm:grid-cols-2">
										<div>
											<label for={`fb-kind-${index}`} class={LABEL_CLS}>Tipo</label>
											<select
												id={`fb-kind-${index}`}
												name="fb_kind"
												bind:value={page.kind}
												class={INPUT_CLS}
											>
												<option value="page">Página</option>
												<option value="group">Grupo</option>
											</select>
										</div>
										<div>
											<label for={`fb-page-${index}`} class={LABEL_CLS}>Page ID</label>
											<input
												id={`fb-page-${index}`}
												name="fb_page_id"
												type="text"
												bind:value={page.page_id}
												placeholder="1234567890"
												class={INPUT_CLS}
											/>
										</div>
										<div>
											<label for={`fb-token-${index}`} class={LABEL_CLS}>Token de acceso</label>
											<input
												id={`fb-token-${index}`}
												name="fb_token"
												type="text"
												bind:value={page.token}
												class={INPUT_CLS}
											/>
										</div>
										<div>
											<label for={`fb-label-${index}`} class={LABEL_CLS}>Etiqueta</label>
											<input
												id={`fb-label-${index}`}
												name="fb_label"
												type="text"
												bind:value={page.label}
												placeholder="Opcional"
												class={INPUT_CLS}
											/>
										</div>
									</div>
									<div class="mt-3 flex gap-2">
										<button
											type="submit"
											formaction="?/test-facebook"
											name="probe_row"
											value={index}
											disabled={submitting}
											class={PROBE_BTN_CLS}
										>
											Probar
										</button>
										<button
											type="button"
											onclick={() => removePage(index)}
											disabled={submitting}
											class="btn-small btn-delete rounded-full border border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-warm hover:text-danger disabled:opacity-60"
										>
											Eliminar
										</button>
									</div>
									{#if form?.action === 'test-facebook' && form.index === index}
										{#if form.ok}
											<p class="mt-2 text-xs text-success">
												Página verificada{form.page_name ? `: ${form.page_name}` : ''}
											</p>
										{:else}
											<p class="mt-2 text-xs text-danger">Error: {form.message}</p>
										{/if}
									{/if}
								</div>
							{/each}
						</div>
						<button
							type="button"
							onclick={addPage}
							disabled={submitting}
							class="mt-3 rounded-full border border-dashed border-line px-3 py-1.5 text-xs font-medium text-muted transition-colors hover:bg-surface-warm disabled:opacity-60"
						>
							+ Agregar página o grupo
						</button>
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
	</div>
</div>
