<script lang="ts">
	import {
		formatDisplayDateTime,
		sentimentBadgeClass,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const SKELETON_CLS = 'animate-pulse rounded-lg bg-slate-100';
</script>

<svelte:head>
	<title>Evento | Media Monitor</title>
</svelte:head>

<a
	href="/events"
	class="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900"
>
	← Volver a eventos
</a>

{#await data.event}
	<div class="mt-4 rounded-xl border border-slate-200 bg-white p-6" aria-busy="true">
		<span class="sr-only">Cargando evento…</span>
		<div class={`${SKELETON_CLS} h-4 w-3/4`} aria-hidden="true"></div>
		<div class={`${SKELETON_CLS} mt-3 h-3 w-1/2`} aria-hidden="true"></div>
	</div>
{:then event}
	<div class="mt-4 flex flex-wrap items-end justify-between gap-3">
		<div>
			<h1 class="text-2xl font-semibold tracking-tight">{event.title}</h1>
			<p class="mt-1 text-sm text-slate-500">
				<span class="tabular-nums"
					>{event.mention_count}
					{event.mention_count === 1 ? 'mención' : 'menciones'}</span
				>
				·
				<span class="tabular-nums"
					>{event.source_count} {event.source_count === 1 ? 'fuente' : 'fuentes'}</span
				>
				· Visto por última vez
				<time datetime={event.last_seen_at} class="tabular-nums"
					>{formatDisplayDateTime(event.last_seen_at)}</time
				>
			</p>
		</div>
	</div>

	{#if event.summary?.trim()}
		<div class="mt-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
			<h2 class="text-xs font-medium uppercase tracking-wide text-slate-500">Resumen del evento</h2>
			<p class="mt-1 text-sm text-slate-700">{event.summary}</p>
		</div>
	{/if}

	<section class="mt-8" aria-labelledby="event-mentions-heading">
		<h2 id="event-mentions-heading" class="text-lg font-semibold tracking-tight">Menciones</h2>
		{#if event.mentions.length === 0}
			<p class="mt-3 text-sm text-slate-500">Sin menciones asociadas.</p>
		{:else}
			<ul class="mt-3 grid gap-2" aria-label="Menciones del evento">
				{#each event.mentions as mention (mention.id)}
					<li
						class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm"
					>
						<span
							class="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 ring-1 ring-inset ring-slate-500/20"
						>
							{sourceLabel(mention.source)}
						</span>
						<span
							class={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${sentimentBadgeClass(mention.sentiment)}`}
						>
							{mention.sentiment ? sentimentLabel(mention.sentiment) : sentimentLabel(null)}
						</span>
						<a
							href={mention.url}
							target="_blank"
							rel="noopener noreferrer"
							aria-label={`${mention.title ?? mention.url} (abre en una pestaña nueva)`}
							class="font-medium text-slate-900 hover:underline"
						>
							{mention.title ?? mention.url}
						</a>
						{#if mention.published_at}
							<time datetime={mention.published_at} class="ml-auto text-xs tabular-nums text-slate-500">
								{formatDisplayDateTime(mention.published_at)}
							</time>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{:catch cause}
	<div class="mt-4 rounded-xl border border-dashed border-red-300 bg-white p-6" role="alert">
		<p class="text-sm font-medium text-red-700">No se pudo cargar el evento.</p>
		<p class="mt-1 text-sm text-red-600/80">{cause?.message ?? 'Error desconocido'}</p>
	</div>
{/await}

<section class="mt-8" aria-labelledby="event-coverage-heading">
	<h2 id="event-coverage-heading" class="text-lg font-semibold tracking-tight">Cobertura</h2>
	{#await data.coverage}
		<div class="mt-3 rounded-xl border border-slate-200 bg-white p-6" aria-busy="true">
			<span class="sr-only">Cargando cobertura…</span>
			<div class={`${SKELETON_CLS} h-3 w-2/3`} aria-hidden="true"></div>
			<div class={`${SKELETON_CLS} mt-2 h-3 w-1/2`} aria-hidden="true"></div>
		</div>
	{:then coverage}
		{#if coverage.by_source.length === 0}
			<p class="mt-3 text-sm text-slate-500">Sin cobertura registrada para este evento.</p>
		{:else}
			<p class="mt-1 text-sm text-slate-500">
				<span class="tabular-nums">{coverage.mention_count} menciones</span> en
				<span class="tabular-nums">{coverage.outlet_count} medios</span>
			</p>
			<div class="mt-3 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
				<table class="min-w-full text-sm">
					<caption class="sr-only">Cobertura del evento por fuente</caption>
					<thead>
						<tr
							class="border-b border-slate-200 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500"
						>
							<th scope="col" class="px-3 py-2 font-medium">Fuente</th>
							<th scope="col" class="px-3 py-2 font-medium">Menciones</th>
							<th scope="col" class="px-3 py-2 font-medium">Medios</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-slate-100">
						{#each coverage.by_source as row (row.source)}
							<tr>
								<th scope="row" class="px-3 py-2 text-left font-medium text-slate-700">
									{sourceLabel(row.source)}
								</th>
								<td class="px-3 py-2 tabular-nums text-slate-600">{row.n_mentions}</td>
								<td class="px-3 py-2 tabular-nums text-slate-600">{row.outlets}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	{:catch cause}
		<div class="mt-3 rounded-xl border border-dashed border-red-300 bg-white p-6" role="alert">
			<p class="text-sm font-medium text-red-700">No se pudo cargar la cobertura.</p>
			<p class="mt-1 text-sm text-red-600/80">{cause?.message ?? 'Error desconocido'}</p>
		</div>
	{/await}
</section>
