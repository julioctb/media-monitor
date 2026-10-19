<script lang="ts">
	import {
		formatDisplayDateTime,
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

	const SENTIMENT_CHIP_CLS: Record<string, string> = {
		positive: 'border-success/40 bg-success/10 text-success',
		negative: 'border-danger/40 bg-danger/10 text-danger',
		neutral: 'border-line bg-surface text-muted'
	};

	function sentimentChipClass(value: string): string {
		return SENTIMENT_CHIP_CLS[value] ?? 'border-line bg-surface text-muted';
	}

	function initials(name: string): string {
		return name
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((word) => word[0]?.toUpperCase() ?? '')
			.join('');
	}
</script>

<svelte:head>
	<title>{person.name} | Media Monitor</title>
</svelte:head>

<a href="/persons" class="text-sm font-medium text-muted transition-colors hover:text-ink">
	← Volver a personas
</a>

<header class="mt-4 flex flex-wrap items-center justify-between gap-6">
	<div class="flex items-center gap-4">
		<span class="monogram text-base" aria-hidden="true">{initials(person.name)}</span>
		<div>
			<h1 class="page-title">{person.name}</h1>
			{#if person.role || person.org}
				<p class="lead">
					{[person.role, person.org].filter(Boolean).join(' · ')}
				</p>
			{/if}
			{#if person.aliases.length > 0}
				<p class="mt-1 text-xs text-meta">También: {person.aliases.join(', ')}</p>
			{/if}
		</div>
	</div>
	<div class="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Estadísticas históricas de menciones">
		<div class="rounded-2xl border border-line-soft bg-white px-5 py-4 text-center">
			<strong class="block text-2xl font-semibold tabular-nums text-ink">
				{person.mention_count}
			</strong>
			<span class="text-xs text-muted">Menciones totales</span>
		</div>
		{#each Object.entries(sentimentCounts) as [sentiment, count] (sentiment)}
			<div class="rounded-2xl border border-line-soft bg-white px-5 py-4 text-center">
				<strong
					class={`block text-2xl font-semibold tabular-nums ${
						sentiment === 'positive'
							? 'text-success'
							: sentiment === 'negative'
								? 'text-danger'
								: 'text-muted'
					}`}
				>
					{count}
				</strong>
				<span class="text-xs text-muted">
					{sentiment === 'positive' ? 'Positivas' : sentiment === 'negative' ? 'Negativas' : 'Neutras'}
				</span>
			</div>
		{/each}
	</div>
</header>

<section class="panel mt-6" aria-labelledby="person-timeline-title">
	<div class="panel-head">
		<h2 class="panel-title" id="person-timeline-title">Timeline de menciones</h2>
		<p class="panel-note" role="status" aria-live="polite">
			{person.timeline.length}
			{person.timeline.length === 1 ? 'mención registrada' : 'menciones registradas'}
		</p>
	</div>
	{#if person.timeline.length === 0}
		<p class="empty mt-4">Sin menciones registradas.</p>
	{:else}
		<ol class="mt-4 space-y-3" aria-label="Menciones de la persona">
			{#each person.timeline as item (item.mention_id)}
				<li class="rounded-2xl border border-line-soft bg-white p-5">
					<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-meta">
						<span class="rounded-full bg-surface px-2.5 py-1 font-medium text-ink-2">
							{sourceLabel(item.source)}
						</span>
						{#if item.sentiment}
							<span
								class={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-medium ${sentimentChipClass(item.sentiment)}`}
							>
								{sentimentLabel(item.sentiment)}
							</span>
						{/if}
						<time datetime={item.published_at ?? item.ingested_at} class="tabular-nums">
							{formatDisplayDateTime(item.published_at ?? item.ingested_at)}
						</time>
					</div>
					<h3 class="mt-2 text-sm font-semibold text-ink">
						<a
							href={item.url}
							target="_blank"
							rel="noopener noreferrer"
							aria-label={`${item.title ?? item.url} (abre en una pestaña nueva)`}
							class="underline decoration-line underline-offset-[3px] hover:decoration-ink"
						>
							{item.title ?? item.url}
						</a>
					</h3>
					{#if item.role}
						<p class="mt-1 text-xs text-muted">Como: {item.role}</p>
					{/if}
					{#if item.context}
						<blockquote class="mt-2 border-l-2 border-line pl-4 text-sm text-ink-2">
							{item.context}
						</blockquote>
					{/if}
					{#if item.event_id && item.event_title}
						<a
							href={`/events/${item.event_id}`}
							class="mt-2 inline-block text-xs font-medium text-accent hover:text-accent-hover"
						>
							Evento: {item.event_title}
						</a>
					{/if}
				</li>
			{/each}
		</ol>
	{/if}
</section>
