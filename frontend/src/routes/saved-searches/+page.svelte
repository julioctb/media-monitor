<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';

	import { INPUT_CLS } from '$lib/ui';
	import { sourceLabel } from '$lib/format';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const BTN_CLS = 'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors';

	const UNREADY_HINTS: Record<string, string> = {
		x_twitter: 'falta el token del provider (env X_PROVIDER_API_KEY)',
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

<h1 class="text-2xl font-semibold tracking-tight">Búsquedas guardadas</h1>
<p class="mt-1 text-sm text-slate-500">
	Consultas almacenadas que alimentan la detección de picos y las alertas por cambio de sentimiento.
</p>

{#if form}
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
	action="?/create"
	class="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
>
	<div class="grid gap-3 md:grid-cols-2">
		<div>
			<label for="ss-name" class="mb-1 block text-xs font-medium text-slate-500">Nombre</label>
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
			<label for="ss-query" class="mb-1 block text-xs font-medium text-slate-500">
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
		<legend class="mb-1 block text-xs font-medium text-slate-500">Fuentes (ninguna = todas)</legend>
		<div class="flex flex-wrap gap-3">
			{#each data.sources as source (source)}
				<label
					class={`flex items-center gap-1.5 text-sm ${isReady(source) ? 'text-slate-700' : 'text-slate-400'}`}
				>
					<input
						type="checkbox"
						name={`src_${source}`}
						value="1"
						disabled={!isReady(source)}
						title={isReady(source) ? '' : `Sin configurar: ${UNREADY_HINTS[source] ?? ''}`}
						class="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-300 disabled:cursor-not-allowed"
					/>
					{sourceLabel(source)}
				</label>
			{/each}
		</div>
		{#if unreadySources.length > 0}
			<p class="mt-2 text-xs text-amber-600">
				Sin ingesta activa:
				{unreadySources.map((source) => `${sourceLabel(source)} (${UNREADY_HINTS[source]})`).join(' ·')}.
				Configura la fuente en Ajustes para poder seleccionarla.
			</p>
		{/if}
	</fieldset>

	<div class="mt-3 grid gap-3 sm:grid-cols-3">
		<div>
			<label for="ss-classifier" class="mb-1 block text-xs font-medium text-slate-500">
				Clasificador (opcional)
			</label>
			<input id="ss-classifier" name="classifier" maxlength={32} placeholder="political" class={INPUT_CLS} />
		</div>
		<div>
			<label for="ss-label" class="mb-1 block text-xs font-medium text-slate-500">
				Etiqueta (opcional)
			</label>
			<input id="ss-label" name="label" maxlength={32} placeholder="political" class={INPUT_CLS} />
		</div>
		<div>
			<label for="ss-range" class="mb-1 block text-xs font-medium text-slate-500">
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
		class="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
	>
		Crear búsqueda guardada
	</button>
</form>

{#if data.savedSearches.length === 0}
	<div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
		<p class="text-sm font-medium text-slate-700">Todavía no hay búsquedas guardadas.</p>
		<p class="mt-1 text-sm text-slate-500">Crea la primera con el formulario de arriba.</p>
	</div>
{:else}
	<ul class="mt-6 divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
		{#each data.savedSearches as search (search.id)}
			<li class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
				<div class="min-w-0">
					<div class="flex flex-wrap items-center gap-2">
						<span class="text-sm font-medium text-slate-900">{search.name}</span>
						{#if !search.is_active}
							<span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">Pausada</span>
						{/if}
					</div>
					<p class="mt-0.5 truncate text-xs text-slate-500">“{search.query}”</p>
					<p class="mt-0.5 text-xs text-slate-400">
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
					<form method="POST" action="?/toggle">
						<input type="hidden" name="id" value={search.id} />
						<input type="hidden" name="is_active" value={search.is_active ? '0' : '1'} />
						<button type="submit" class={`${BTN_CLS} border-slate-300 text-slate-600 hover:bg-slate-50`}>
							{search.is_active ? 'Pausar' : 'Activar'}
						</button>
					</form>
					<form method="POST" action="?/delete">
						<input type="hidden" name="id" value={search.id} />
						<button type="submit" class={`${BTN_CLS} border-red-200 text-red-600 hover:bg-red-50`}>
							Eliminar
						</button>
					</form>
				</div>
			</li>
		{/each}
	</ul>
{/if}
