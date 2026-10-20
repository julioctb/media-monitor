<script lang="ts">
	import {
		formatDisplayDateTime,
		formatDisplayDateTimeAt,
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
	← Volver a actores
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
		<div class="profile-stat">
			<strong>{person.mention_count}</strong>
			<span>Menciones totales</span>
		</div>
		{#each Object.entries(sentimentCounts) as [sentiment, count] (`${sentiment}-${count}`)}
			<div class={`profile-stat ${sentiment}-stat`}>
				<strong>{count}</strong>
				<span>
					{sentiment === 'positive' ? 'Positivas' : sentiment === 'negative' ? 'Negativas' : 'Neutras'}
				</span>
			</div>
		{/each}
	</div>
</header>

<section class="timeline-section" aria-labelledby="person-timeline-title">
	<h2 id="person-timeline-title">Cronología de menciones</h2>
	<p class="support" role="status" aria-live="polite">
		{person.timeline.length}
		{person.timeline.length === 1 ? 'mención registrada' : 'menciones registradas'}
	</p>
	{#if person.timeline.length === 0}
		<p class="empty mt-4">Sin menciones registradas.</p>
	{:else}
		<ol class="timeline" aria-label="Menciones de la persona">
			{#each person.timeline as item (item.mention_id)}
				<li>
					<article class="mention">
						<div class="mention-top">
							<span class="tag">{sourceLabel(item.source)}</span>
							{#if item.sentiment}
								<span class={`tag tone ${item.sentiment}`}>{sentimentLabel(item.sentiment)}</span>
							{/if}
							<time datetime={item.published_at ?? item.ingested_at}>
								{formatDisplayDateTimeAt(item.published_at ?? item.ingested_at)}
							</time>
						</div>
						<h3>
							<a
								href={item.url}
								target="_blank"
								rel="noopener noreferrer"
								aria-label={`${item.title ?? item.url} (abre en una pestaña nueva)`}
								class="text-ink underline decoration-line underline-offset-[3px] hover:decoration-ink"
							>
								{item.title ?? item.url}
							</a>
						</h3>
						{#if item.role}
							<p class="mention-role">Como: {item.role}</p>
						{/if}
						{#if item.context}
							<p class="excerpt">{item.context}</p>
						{/if}
						{#if item.event_id && item.event_title}
							<p class="event-ref">
								<strong>Evento:</strong>
								<a
									href={`/events/${item.event_id}`}
									class="text-accent hover:text-accent-hover"
								>
									{item.event_title}
								</a>
							</p>
						{/if}
					</article>
				</li>
			{/each}
		</ol>
	{/if}
</section>

			<p class="sample-note">
				Los recuentos corresponden al histórico completo del cliente; el timeline refleja las
				menciones vinculadas al actor durante el enriquecimiento.
			</p>
