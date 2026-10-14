<script lang="ts">
	import {
		formatDisplayDateTime,
		sentimentBadgeClass,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const person = $derived(data.person);

	const sentimentCounts = $derived.by(() => {
		const counts: Record<string, number> = { positive: 0, negative: 0, neutral: 0 };
		for (const item of person.timeline) {
			if (item.sentiment) counts[item.sentiment] += 1;
		}
		return counts;
	});
</script>

<svelte:head>
	<title>{person.name} | Media Monitor</title>
</svelte:head>

<a href="/persons" class="text-sm text-slate-500 hover:text-slate-900">← Personas</a>

<div class="mt-2 flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">{person.name}</h1>
		{#if person.role || person.org}
			<p class="mt-1 text-sm text-slate-500">
				{[person.role, person.org].filter(Boolean).join(' · ')}
			</p>
		{/if}
	</div>
	<div class="flex items-center gap-4 text-xs text-slate-500">
		<span class="tabular-nums">{person.mention_count} menciones</span>
		{#each Object.entries(sentimentCounts) as [sentiment, count] (sentiment)}
			{#if count > 0}
				<span
					class={`inline-flex items-center rounded-full px-2 py-0.5 font-medium ring-1 ring-inset ${sentimentBadgeClass(sentiment)}`}
				>
					{sentimentLabel(sentiment)}: <span class="ml-1 tabular-nums">{count}</span>
				</span>
			{/if}
		{/each}
	</div>
</div>

{#if person.aliases.length > 0}
	<p class="mt-2 text-xs text-slate-400">También: {person.aliases.join(', ')}</p>
{/if}

<h2 class="mt-8 text-sm font-semibold text-slate-900">Timeline de menciones</h2>
{#if person.timeline.length === 0}
	<p class="mt-2 text-sm text-slate-500">Sin menciones registradas.</p>
{:else}
	<ol class="mt-3 space-y-3" aria-label="Menciones de la persona">
		{#each person.timeline as item (item.mention_id)}
			<li class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
				<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
					<span
						class="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-500/20"
					>
						{sourceLabel(item.source)}
					</span>
					{#if item.sentiment}
						<span
							class={`inline-flex items-center rounded-full px-2 py-0.5 font-medium ring-1 ring-inset ${sentimentBadgeClass(item.sentiment)}`}
						>
							{sentimentLabel(item.sentiment)}
						</span>
					{/if}
					<time datetime={item.published_at ?? item.ingested_at} class="tabular-nums">
						{formatDisplayDateTime(item.published_at ?? item.ingested_at)}
					</time>
				</div>
				<h3 class="mt-1 text-sm font-semibold text-slate-900">
					<a
						href={item.url}
						target="_blank"
						rel="noopener noreferrer"
						aria-label={`${item.title ?? item.url} (abre en una pestaña nueva)`}
						class="hover:underline"
					>
						{item.title ?? item.url}
					</a>
				</h3>
				{#if item.role}
					<p class="mt-1 text-xs text-slate-500">Como: {item.role}</p>
				{/if}
				{#if item.context}
					<blockquote class="mt-1 border-l-2 border-slate-200 pl-3 text-sm text-slate-600">
						{item.context}
					</blockquote>
				{/if}
				{#if item.event_id && item.event_title}
					<a
						href={`/events/${item.event_id}`}
						class="mt-1 inline-block text-xs text-amber-700 hover:underline"
					>
						Evento: {item.event_title}
					</a>
				{/if}
			</li>
		{/each}
	</ol>
{/if}
