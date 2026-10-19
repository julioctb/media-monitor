<script lang="ts">
	import { page } from '$app/state';
	import EventGroup from '$lib/components/EventGroup.svelte';
	import FeedFilterBar from '$lib/components/FeedFilterBar.svelte';
	import { groupByEvent } from '$lib/grouping';
	import type { FeedGroup } from '$lib/grouping';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const digest = $derived(data.digest);
	const digestModeLabel: Record<string, string> = { heuristic: 'Plantilla', llm: 'IA' };

	const keywordNames = $derived(new Map(data.keywords.map((k) => [k.id, k.text])));

	/** Same event = same story: one card plus a collapsed coverage list. */
	const groups = $derived(groupByEvent(data.mentions.items));

	function keywordLabelFor(group: FeedGroup): string | null {
		const keywordId = group.mentions[0]?.keyword_id ?? null;
		return keywordId !== null ? (keywordNames.get(keywordId) ?? null) : null;
	}

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

{#if digest}
	<section
		aria-label="Digest del día"
		class="mt-4 rounded-xl border border-slate-200 bg-slate-900 p-5 text-white shadow-sm"
	>
		<div class="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
			<span>Digest {digest.summary_date}</span>
			<span
				class="rounded-full px-2 py-0.5 text-[11px] font-medium
				{digest.mode === 'llm' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-300'}"
			>
				{digestModeLabel[digest.mode] ?? digest.mode}
			</span>
		</div>
		<p class="mt-2 line-clamp-3 text-sm leading-relaxed">{digest.narrative}</p>
		<a
			href="/"
			class="mt-2 inline-block text-xs font-medium text-sky-300 underline-offset-2 hover:underline"
		>
			Ver digest completo →
		</a>
	</section>
{/if}

<FeedFilterBar
	sources={data.sources}
	keywords={data.keywords}
	filters={data.filters}
	resetHref={page.url.pathname}
/>

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
		{#each groups as group (group.key)}
			<li>
				<EventGroup {group} keywordLabel={keywordLabelFor(group)} />
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
