<script lang="ts">
	import { enhance } from '$app/forms';
	import { formatDisplayDateTime } from '$lib/format';

	import { INPUT_CLS } from '$lib/ui';
	import { sourceLabel } from '$lib/format';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	/** Gates the create submit while its action is in flight. */
	let creating = $state(false);

	const BTN_CLS = 'rounded-full border px-3 py-1.5 text-xs font-medium transition-colors';

	const UNREADY_HINTS: Record<string, string> = {
		x_twitter: 'falta el token del proveedor (env X_PROVIDER_API_KEY)',
		facebook_page: 'no hay páginas FB en Ajustes',
		rss_custom: 'no hay feeds RSS en Ajustes',
		gdelt: 'GDELT desactivado en Ajustes',
		news_rss: ''
	};

	const readiness = $derived(data.sourceReadiness ?? {});
	const isReady = (source: string) => readiness[source] !== false;
	const unreadySources = $derived(
		data.sources.filter((source: string) => !isReady(source) && UNREADY_HINTS[source])
	);
</script>

<svelte:head>
	<title>Búsquedas guardadas | Media Monitor</title>
</svelte:head>

<h1 class="page-title">Búsquedas guardadas</h1>
<p class="lead">
	Consultas almacenadas que alimentan la detección de picos y las alertas por cambio de sentimiento.
</p>

{#if form}
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

<form
	method="POST"
	action="?/create"
	class="filter-panel"
	use:enhance={() => {
		creating = true;
		return async ({ update }) => {
			// Default reset on success is fine: the input recalls its value from
			// `form` only on failure.
			await update();
			creating = false;
		};
	}}
>
	<div class="grid gap-3 md:grid-cols-2">
		<div>
			<label for="ss-name" class="mb-1 block text-xs font-medium text-ink-2">Nombre</label>
			<input
				id="ss-name"
				name="name"
				value={form?.action === 'create' && !form.ok ? form.name : ''}
				maxlength={200}
				required
				placeholder="p. ej. Menciones de marca"
				class={INPUT_CLS}
			/>
		</div>
		<div>
			<label for="ss-query" class="mb-1 block text-xs font-medium text-ink-2">
				Consulta (coincide en título y contenido)
			</label>
			<input
				id="ss-query"
				name="query"
				maxlength={500}
				required
				placeholder="p. ej. &quot;Acme Corp&quot;"
				class={INPUT_CLS}
			/>
		</div>
	</div>

	<fieldset class="mt-3">
		<legend class="mb-1 block text-xs font-medium text-ink-2">Fuentes (ninguna = todas)</legend>
		<div class="flex flex-wrap gap-3">
			{#each data.sources as source (source)}
				<label
					class={`flex items-center gap-1.5 text-sm ${isReady(source) ? 'text-ink-2' : 'text-meta'}`}
				>
					<input
						type="checkbox"
						name={`src_${source}`}
						value="1"
						disabled={!isReady(source)}
						title={isReady(source) ? '' : `Sin configurar: ${UNREADY_HINTS[source] ?? ''}`}
						class="size-4 rounded border-line accent-accent disabled:cursor-not-allowed"
					/>
					{sourceLabel(source)}
				</label>
			{/each}
		</div>
		{#if unreadySources.length > 0}
			<p class="mt-2 text-xs text-muted"><span class="font-semibold text-ink-2">Sin ingesta activa:</span>
				{unreadySources.map((source) => `${sourceLabel(source)} (${UNREADY_HINTS[source]})`).join(' · ')}.
				Configura la fuente en Ajustes para poder seleccionarla.
			</p>
		{/if}
	</fieldset>

	<div class="mt-3 grid gap-3 sm:grid-cols-3">
		<div>
			<label for="ss-classifier" class="mb-1 block text-xs font-medium text-ink-2">
				Clasificador (opcional)
			</label>
			<input id="ss-classifier" name="classifier" maxlength={32} placeholder="political" class={INPUT_CLS} />
		</div>
		<div>
			<label for="ss-label" class="mb-1 block text-xs font-medium text-ink-2">
				Etiqueta (opcional)
			</label>
			<input id="ss-label" name="label" maxlength={32} placeholder="political" class={INPUT_CLS} />
		</div>
		<div>
			<label for="ss-range" class="mb-1 block text-xs font-medium text-ink-2">
				Rango por defecto (días)
			</label>
			<input
				id="ss-range"
				name="range_days"
				type="number"
				min={1}
				max={365}
				value={7}
				class={INPUT_CLS}
			/>
		</div>
	</div>

	<button
		type="submit"
		disabled={creating}
		class="mt-4 inline-flex min-h-[44px] items-center justify-center rounded-full border border-accent bg-accent px-[22px] text-sm font-semibold text-accent-on transition-colors hover:border-accent-hover hover:bg-accent-hover active:border-accent-active active:bg-accent-active disabled:opacity-60"
	>
		Crear búsqueda guardada
	</button>
</form>

{#if data.savedSearches.length === 0}
	<div class="empty mt-6">
		<p class="text-sm font-medium text-ink-2">Todavía no hay búsquedas guardadas.</p>
		<p class="lead">Crea la primera con el formulario de arriba.</p>
	</div>
{:else}
	<ul class="mt-6 divide-y divide-line-soft rounded-2xl border border-line-soft bg-white">
		{#each data.savedSearches as search (search.id)}
			<li class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
				<div class="min-w-0">
					<div class="flex flex-wrap items-center gap-2">
						<span class="text-sm font-medium text-ink">{search.name}</span>
						{#if !search.is_active}
							<span class="rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-muted">Pausada</span>
						{/if}
					</div>
					<p class="mt-0.5 truncate text-xs text-muted">“{search.query}”</p>
					<p class="mt-0.5 text-xs text-meta">
						{search.sources.length === 0
							? 'Todas las fuentes'
							: search.sources.map((source) => sourceLabel(source)).join(', ')}
						{#if search.classifier || search.label}
							· clasificador {search.classifier ?? '—'} / etiqueta {search.label ?? '—'}
						{/if}
						· creada {formatDisplayDateTime(search.created_at)}
					</p>
				</div>

				<div class="flex gap-2">
					<form method="POST" action="?/toggle" use:enhance>
						<input type="hidden" name="id" value={search.id} />
						<input type="hidden" name="is_active" value={search.is_active ? '0' : '1'} />
						<button type="submit" class={`${BTN_CLS} border-line text-ink-2 hover:bg-surface-warm`}>
							{search.is_active ? 'Pausar' : 'Activar'}
						</button>
					</form>
					<form method="POST" action="?/delete" use:enhance>
						<input type="hidden" name="id" value={search.id} />
						<button type="submit" class={`${BTN_CLS} border-danger/40 text-danger hover:bg-danger/10`}>
							Eliminar
						</button>
					</form>
				</div>
			</li>
		{/each}
	</ul>
{/if}
