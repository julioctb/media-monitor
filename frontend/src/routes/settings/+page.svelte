<script lang="ts">
	import { enhance } from '$app/forms';

	import { INPUT_CLS } from '$lib/ui';
	import type { AvailableScraper, ClientSettings } from '$lib/api';
	import type { PageProps, SubmitFunction } from './$types';

	let { data, form }: PageProps = $props();

	const LABEL_CLS = 'mb-1 block text-xs font-medium text-slate-500';
	const CHECK_CLS = 'size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-300';
	const PROBE_BTN_CLS =
		'rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 transition-colors hover:bg-slate-50 disabled:opacity-60';

	const TIMEZONES = ['America/Mexico_City', 'America/Monterrey', 'America/Tijuana', 'UTC'];

	interface PageDraft {
		page_id: string;
		token: string;
		label: string;
	}

	interface SettingsDraft {
		client_name: string;
		timezone: string;
		/** Kept as text: the action parses it, '' surfaces a friendly error. */
		retention_days: string;
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
		ai_fallback_local: boolean;
	}

	function toDraft(settings: ClientSettings): SettingsDraft {
		return {
			client_name: settings.client_name,
			timezone: settings.timezone,
			retention_days: String(settings.retention_days),
			gdelt_enabled: settings.gdelt_enabled,
			pages: settings.facebook_pages.map((page) => ({ ...page })),
			rss: settings.rss_feeds.join('\n'),
			scrapers: [...settings.scrapers],
			ai_provider: settings.ai_provider,
			ai_base_url: settings.ai_base_url ?? '',
			ai_model: settings.ai_model ?? '',
			ai_api_key: settings.ai_api_key ?? '',
			ai_fallback_local: settings.ai_fallback_local
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

	function markDirty(): void {
		dirty = true;
	}

	function addPage(): void {
		draft.pages.push({ page_id: '', token: '', label: '' });
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

<h1 class="text-2xl font-semibold tracking-tight">Configuración</h1>
<p class="mt-1 text-sm text-slate-500">
	Fuentes de ingesta, retención y proveedor de análisis de sentimiento.
</p>

{#if form?.action === 'save'}
	<div
		role={form.ok ? 'status' : 'alert'}
		class={`mt-4 rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${
			form.ok
				? 'bg-green-50 text-green-800 ring-green-600/20'
				: 'bg-red-50 text-red-800 ring-red-600/20'
		}`}
	>
		{form.message}
	</div>
{/if}

<form
	method="POST"
	action="?/save"
	class="mt-6 space-y-6"
	oninput={markDirty}
	onchange={markDirty}
	use:enhance={handleSubmit}
>
	<!-- Hidden default submitter: Enter in any field saves instead of probing. -->
	<button type="submit" tabindex="-1" aria-label="Guardar" class="hidden"></button>

	<!-- General -->
	<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
		<h2 class="text-base font-semibold text-slate-900">General</h2>
		<div class="mt-4 grid gap-4 sm:grid-cols-2">
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
			</div>
			<div class="sm:col-span-2">
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
				<p class="mt-1 text-xs text-slate-500">0 desactiva el purge.</p>
			</div>
		</div>
	</section>

	<!-- Fuentes -->
	<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
		<h2 class="text-base font-semibold text-slate-900">Fuentes</h2>
		<div class="mt-4 space-y-6">
			<div>
				<h3 class="text-sm font-medium text-slate-700">Páginas de Facebook</h3>
				{#if draft.pages.length === 0}
					<p class="mt-2 text-sm text-slate-500">
						No hay páginas configuradas. Agrega una con su page_id y un token de acceso con
						permiso de lectura.
					</p>
				{/if}
				<div class="mt-3 space-y-3">
					{#each draft.pages as page, index (page)}
						<div class="rounded-lg border border-slate-200 p-3">
							<div class="grid gap-3 sm:grid-cols-3">
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
									class="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-500 transition-colors hover:bg-slate-50 hover:text-red-600 disabled:opacity-60"
								>
									Eliminar
								</button>
							</div>
							{#if form?.action === 'test-facebook' && form.index === index}
								{#if form.ok}
									<p class="mt-2 text-xs text-green-700">
										Página verificada{form.page_name ? `: ${form.page_name}` : ''}
										{#if form.page_link}
											&middot;
											<a
												href={form.page_link}
												target="_blank"
												rel="noreferrer"
												class="underline hover:text-green-900">{form.page_link}</a
											>
										{/if}
									</p>
								{:else}
									<p class="mt-2 text-xs text-red-700">Error: {form.message}</p>
								{/if}
							{/if}
						</div>
					{/each}
				</div>
				<button
					type="button"
					onclick={addPage}
					disabled={submitting}
					class="mt-3 rounded-md border border-dashed border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-600 transition-colors hover:bg-slate-50 disabled:opacity-60"
				>
					+ Agregar página
				</button>
			</div>

			<div>
				<label for="set-rss" class="text-sm font-medium text-slate-700">Feeds RSS</label>
				<textarea
					id="set-rss"
					name="rss_feeds"
					rows="4"
					bind:value={draft.rss}
					placeholder={'https://ejemplo.com/feed.xml\nhttps://otrositio.com/rss'}
					class={`mt-1 ${INPUT_CLS} font-mono text-xs`}
				></textarea>
				{#if draft.rss.trim() === ''}
					<p class="mt-1 text-xs text-slate-500">
						Sin feeds: pega una URL por línea (http/https) para monitorear noticias.
					</p>
				{:else}
					<p class="mt-1 text-xs text-slate-500">Una URL por línea.</p>
				{/if}
			</div>

			<div>
				<h3 class="text-sm font-medium text-slate-700">Scrapers (medios sin RSS)</h3>
				{#if availableScrapers.length === 0}
					<p class="mt-2 text-sm text-slate-500">
						No hay scrapers disponibles en el registro del servidor.
					</p>
				{:else}
					<div class="mt-3 space-y-2">
						{#each availableScrapers as scraper (scraper.name)}
							<label class="flex items-center gap-2 text-sm text-slate-700">
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
									class="text-xs text-slate-400 underline hover:text-slate-600"
								>
									{scraper.base_url}
								</a>
							</label>
						{/each}
					</div>
					<p class="mt-2 text-xs text-slate-500">
						Medios sin feed RSS: el worker revisa su portada en cada ciclo.
					</p>
				{/if}
			</div>

			<label class="flex items-center gap-2 text-sm text-slate-700">
				<input type="checkbox" name="gdelt_enabled" value="1" bind:checked={draft.gdelt_enabled} class={CHECK_CLS} />
				Incluir GDELT
			</label>
		</div>
	</section>

	<!-- Inteligencia -->
	<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
		<h2 class="text-base font-semibold text-slate-900">Inteligencia</h2>
		<div class="mt-4 space-y-2">
			<span id="ai-provider-label" class={LABEL_CLS}>Proveedor de análisis</span>
			<div class="flex gap-4" role="radiogroup" aria-labelledby="ai-provider-label">
				<label class="flex items-center gap-2 text-sm text-slate-700">
					<input
						type="radio"
						name="ai_provider"
						value="local"
						checked={draft.ai_provider === 'local'}
						onchange={() => (draft.ai_provider = 'local')}
						class={CHECK_CLS}
					/>
					Modelo local
				</label>
				<label class="flex items-center gap-2 text-sm text-slate-700">
					<input
						type="radio"
						name="ai_provider"
						value="openai"
						checked={draft.ai_provider === 'openai'}
						onchange={() => (draft.ai_provider = 'openai')}
						class={CHECK_CLS}
					/>
					OpenAI (API)
				</label>
			</div>
		</div>

		<!-- Rendered but hidden for `local`: the values still submit, so
			switching providers never wipes stored credentials. -->
		<div class={draft.ai_provider === 'openai' ? 'mt-4 space-y-4 border-l-2 border-slate-100 pl-4' : 'hidden'}>
			<div>
				<label for="set-ai-base-url" class={LABEL_CLS}>Base URL</label>
				<input
					id="set-ai-base-url"
					name="ai_base_url"
					type="text"
					bind:value={draft.ai_base_url}
					placeholder="https://api.openai.com/v1"
					class={INPUT_CLS}
				/>
			</div>
			<div>
				<label for="set-ai-model" class={LABEL_CLS}>Modelo</label>
				<input
					id="set-ai-model"
					name="ai_model"
					type="text"
					bind:value={draft.ai_model}
					placeholder="gpt-4o-mini"
					class={INPUT_CLS}
				/>
			</div>
			<div>
				<label for="set-ai-key" class={LABEL_CLS}>API key</label>
				<input
					id="set-ai-key"
					name="ai_api_key"
					type="password"
					bind:value={draft.ai_api_key}
					autocomplete="off"
					class={INPUT_CLS}
				/>
			</div>
			<label class="flex items-center gap-2 text-sm text-slate-700">
				<input
					type="checkbox"
					name="ai_fallback_local"
					value="1"
					bind:checked={draft.ai_fallback_local}
					class={CHECK_CLS}
				/>
				Si la API falla usar el modelo local
			</label>
		</div>

		<div class="mt-4">
			<button type="submit" formaction="?/test-ai" disabled={submitting} class={PROBE_BTN_CLS}>
				Probar conexión
			</button>
			{#if form?.action === 'test-ai'}
				{#if form.ok}
					<p class="mt-2 text-xs text-green-700">
						Conexión correcta
						{#if form.engine}
							&middot; {form.engine}
						{/if}
						{#if form.model}
							&middot; {form.model}
						{/if}
						{#if form.latency_ms !== null}
							&middot; {form.latency_ms} ms
						{/if}
						{#if form.label}
							&middot; etiqueta: {form.label}
						{/if}
					</p>
				{:else}
						<p class="mt-2 text-xs text-red-700">Error: {form.message}</p>
						{/if}
						{/if}
						</div>
						</section>

	<div class="flex items-center gap-3">
		<button
			type="submit"
			disabled={submitting}
			class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-slate-700 disabled:opacity-60"
		>
			Guardar configuración
			{#if dirty}
				<span class="ml-1.5 inline-block size-1.5 rounded-full bg-amber-300" title="Cambios sin guardar"></span>
				<span class="sr-only">(cambios sin guardar)</span>
			{/if}
		</button>
	</div>
</form>
