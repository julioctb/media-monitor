<script lang="ts">
	import { page } from '$app/state';
	import MentionCard from '$lib/components/MentionCard.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const INPUT_CLS =
		'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';
	const LABEL_CLS = 'mb-1 block text-xs font-medium text-slate-500';

	const sentimentOptions: Array<{ value: string; label: string }> = [
		{ value: '', label: 'Todos' },
		{ value: 'positive', label: 'Positivo' },
		{ value: 'negative', label: 'Negativo' },
		{ value: 'neutral', label: 'Neutro' },
		{ value: 'none', label: 'Sin clasificar' }
	];
	const limitOptions = [25, 50, 100, 200];

	const keywordNames = $derived(new Map(data.keywords.map((k) => [k.id, k.text])));

	const activeKeywords = $derived(data.keywords.filter((k) => k.is_active));
	const selectedKeywordId = $derived(data.filters.keyword_id ?? '');

	function hrefWithKeyword(keywordId: string | null): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (keywordId === null) params.delete('keyword_id');
		else params.set('keyword_id', keywordId);
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	function hrefWithOffset(offset: number): string {
		const params = new URLSearchParams(page.url.searchParams);
		params.set('offset', String(offset));
		return `${page.url.pathname}?${params.toString()}`;
	}

	const pagination = $derived.by(() => {
		const { limit, offset } = data.filters;
		const total = data.mentions.total;
		return {
			from: total === 0 ? 0 : offset + 1,
			to: Math.min(offset + limit, total),
			hasPrev: offset > 0,
			hasNext: offset + limit < total,
			prevHref: hrefWithOffset(Math.max(0, offset - limit)),
			nextHref: hrefWithOffset(offset + limit)
		};
	});
</script>

<svelte:head>
	<title>Feed | Media Monitor</title>
</svelte:head>

<div class="flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">Feed de menciones</h1>
		<p class="mt-1 text-sm text-slate-500">
			{data.mentions.total}
			{data.mentions.total === 1 ? 'mención' : 'menciones'} en total
		</p>
	</div>
</div>

<!-- Filters: plain GET form, works without JavaScript. -->
<form method="get" class="mt-6 grid gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-4">
	<div>
		<label class={LABEL_CLS} for="f-source">Fuente</label>
		<select id="f-source" name="source" class={INPUT_CLS}>
			<option value="">Todas las fuentes</option>
			{#each data.sources as source (source)}
				<option value={source} selected={data.filters.source === source}>{sourceLabel(source)}</option>
			{/each}
		</select>
	</div>

	<div>
		<label class={LABEL_CLS} for="f-sentiment">Sentimiento</label>
		<select id="f-sentiment" name="sentiment" class={INPUT_CLS}>
			{#each sentimentOptions as option (option.value)}
				<option value={option.value} selected={data.filters.sentiment === option.value}>
					{option.label}
				</option>
			{/each}
		</select>
	</div>

	<div>
		<label class={LABEL_CLS} for="f-keyword">Palabra clave</label>
		<select id="f-keyword" name="keyword_id" class={INPUT_CLS}>
			<option value="">Todas</option>
			{#each data.keywords as keyword (keyword.id)}
				<option value={String(keyword.id)} selected={data.filters.keyword_id === String(keyword.id)}>
					{keyword.text}{keyword.is_active ? '' : ' · inactiva'}
				</option>
			{/each}
		</select>
	</div>

	<div>
		<span class={LABEL_CLS}>Clasificación</span>
		<label class="flex items-center gap-2 text-sm text-slate-700">
			<input
				type="checkbox"
				name="political"
				value="1"
				checked={data.filters.political === '1'}
				class="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-200"
			/>
			Solo políticas
		</label>
	</div>

	<div>
		<span class={LABEL_CLS}>Fecha publicación (UTC)</span>
		<div class="flex flex-wrap items-center gap-2">
			<input
				type="date"
				name="since"
				value={data.filters.since}
				aria-label="Desde"
				class={`${INPUT_CLS} min-w-0 flex-1 basis-28`}
			/>
			<span class="text-xs text-slate-400">a</span>
			<input
				type="date"
				name="until"
				value={data.filters.until}
				aria-label="Hasta"
				class={`${INPUT_CLS} min-w-0 flex-1 basis-28`}
			/>
		</div>
	</div>

	<div class="sm:col-span-2">
		<label class={LABEL_CLS} for="f-q">Búsqueda</label>
		<input
			type="search"
			name="q"
			value={data.filters.q}
			placeholder="Buscar en título o contenido"
			class={INPUT_CLS}
		/>
	</div>

	<div>
		<label class={LABEL_CLS} for="f-limit">Por página</label>
		<select id="f-limit" name="limit" class={INPUT_CLS}>
			{#each limitOptions as option (option)}
				<option value={String(option)} selected={data.filters.limit === option}>{option}</option>
			{/each}
		</select>
	</div>

	<div class="flex items-end gap-2">
		<button
			type="submit"
			class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
		>
			Filtrar
		</button>
		<a
			href={page.url.pathname}
			class="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
		>
			Limpiar
		</a>
	</div>
</form>

<!-- Quick keyword pills: same keyword_id param as the form, one source of truth. -->
{#if activeKeywords.length > 0}
	<div class="mt-4 flex flex-wrap items-center gap-2" aria-label="Filtro rápido por palabra clave">
		<span class="text-xs font-medium text-slate-500">Palabras clave:</span>
		<a
			href={hrefWithKeyword(null)}
			class={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
				selectedKeywordId === ''
					? 'bg-slate-900 text-white'
					: 'border border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900'
			}`}
		>
			Todas
		</a>
		{#each activeKeywords as keyword (keyword.id)}
			<a
				href={hrefWithKeyword(String(keyword.id))}
				class={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
					selectedKeywordId === String(keyword.id)
						? 'bg-slate-900 text-white'
						: 'border border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:text-slate-900'
				}`}
			>
				{keyword.text}
			</a>
		{/each}
	</div>
{/if}

{#if data.mentions.items.length === 0}
	<div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
		<p class="text-sm font-medium text-slate-700">Sin menciones para los filtros aplicados.</p>
		<p class="mt-1 text-sm text-slate-500">Ajusta los filtros o espera la próxima ingesta.</p>
	</div>
{:else}
	<ul class="mt-6 grid gap-3" aria-label="Menciones">
		{#each data.mentions.items as mention (mention.id)}
			<li>
				<MentionCard
					{mention}
					keywordLabel={
						mention.keyword_id !== null ? (keywordNames.get(mention.keyword_id) ?? null) : null
					}
				/>
			</li>
		{/each}
	</ul>

	<nav class="mt-6 flex items-center justify-between" aria-label="Paginación">
		<p class="text-xs text-slate-500">
			Mostrando {pagination.from}–{pagination.to} de {data.mentions.total}
		</p>
		<div class="flex gap-2">
			{#if pagination.hasPrev}
				<a
					href={pagination.prevHref}
					class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
				>
					← Anterior
				</a>
			{/if}
			{#if pagination.hasNext}
				<a
					href={pagination.nextHref}
					class="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium text-slate-600 hover:bg-slate-50"
				>
					Siguiente →
				</a>
			{/if}
		</div>
	</nav>
{/if}
