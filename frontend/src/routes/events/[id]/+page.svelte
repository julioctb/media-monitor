<script lang="ts">
	import {
		formatDisplayDateTime,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const SKELETON_CLS = 'animate-pulse rounded-lg bg-surface';

	const SENTIMENT_CHIP_CLS: Record<string, string> = {
		positive: 'border-success/40 bg-success/10 text-success',
		negative: 'border-danger/40 bg-danger/10 text-danger',
		neutral: 'border-line bg-surface text-muted'
	};

	function sentimentChipClass(value: string | null): string {
		return value ? (SENTIMENT_CHIP_CLS[value] ?? 'border-line bg-surface text-muted') : 'border-line text-muted';
	}
</script>

<svelte:head>
	<title>Evento | Media Monitor</title>
</svelte:head>

<a href="/events" class="text-sm font-medium text-muted transition-colors hover:text-ink">
	← Volver a eventos
</a>

{#await data.event}
	<div class="panel mt-4" aria-busy="true">
		<span class="sr-only">Cargando evento…</span>
		<div class={`${SKELETON_CLS} h-4 w-3/4`} aria-hidden="true"></div>
		<div class={`${SKELETON_CLS} mt-3 h-3 w-1/2`} aria-hidden="true"></div>
	</div>
{:then event}
	<header class="mt-4">
		<h1 class="page-title">{event.title}</h1>
		<p class="lead">
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
	</header>

	{#if event.summary?.trim()}
		<!-- Cardless sections: eyebrow heading, bare content (detalle-evento mockup). -->
		<section class="mt-6" aria-labelledby="event-summary-heading">
			<h2 class="eyebrow" id="event-summary-heading">Resumen del evento</h2>
			<p class="mt-2 max-w-prose text-base text-ink-2">{event.summary}</p>
		</section>
	{/if}

	<section class="mt-8" aria-labelledby="event-coverage-heading">
		<h2 class="eyebrow" id="event-coverage-heading">Cobertura</h2>
		{#await data.coverage}
			<div class="mt-4" aria-busy="true">
				<span class="sr-only">Cargando cobertura…</span>
				<div class={`${SKELETON_CLS} h-3 w-2/3`} aria-hidden="true"></div>
				<div class={`${SKELETON_CLS} mt-2 h-3 w-1/2`} aria-hidden="true"></div>
			</div>
		{:then coverage}
			{#if coverage.by_source.length === 0}
				<p class="empty mt-4">Sin cobertura registrada para este evento.</p>
			{:else}
				<p class="mt-2 text-sm text-muted">
					<span class="tabular-nums">{coverage.mention_count} menciones</span> en
					<span class="tabular-nums">{coverage.outlet_count} medios</span>
				</p>
				<div class="table-wrap mt-4">
					<table class="data-table">
						<caption class="sr-only">Cobertura del evento por fuente</caption>
						<thead>
							<tr>
								<th scope="col">Fuente de captura</th>
								<th scope="col">Menciones</th>
								<th scope="col">Medios</th>
							</tr>
						</thead>
						<tbody>
							{#each coverage.by_source as row (row.source)}
								<tr>
									<td data-label="Fuente de captura" class="font-medium text-ink">
										{sourceLabel(row.source)}
									</td>
									<td data-label="Menciones" class="tabular-nums">{row.n_mentions}</td>
									<td data-label="Medios" class="tabular-nums">{row.outlets}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			{/if}
		{:catch cause}
			<div class="empty mt-4 border-danger/40" role="alert">
				<p class="font-medium text-danger">No se pudo cargar la cobertura.</p>
				<p class="mt-1">{cause?.message ?? 'Error desconocido'}</p>
			</div>
		{/await}
	</section>

	<section class="mt-8" aria-labelledby="event-mentions-heading">
		<h2 class="eyebrow" id="event-mentions-heading">Menciones</h2>
		<p class="mt-2 text-sm text-muted" role="status" aria-live="polite">
			{event.mentions.length}
			{event.mentions.length === 1 ? 'mención asociada' : 'menciones asociadas'}
		</p>
		{#if event.mentions.length === 0}
			<p class="empty mt-4">Sin menciones asociadas.</p>
		{:else}
			<ul class="mt-4 grid gap-2" aria-label="Menciones del evento">
				{#each event.mentions as mention (mention.id)}
					<li
						class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-line-soft bg-surface-warm px-3 py-2 text-sm"
					>
						<span class="rounded-full border border-line-soft bg-surface px-2.5 py-1 text-xs font-medium text-ink-2">
							{sourceLabel(mention.source)}
						</span>
						<span
							class={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${sentimentChipClass(mention.sentiment)}`}
						>
							{mention.sentiment ? sentimentLabel(mention.sentiment) : sentimentLabel(null)}
						</span>
						<a
							href={mention.url}
							target="_blank"
							rel="noopener noreferrer"
							aria-label={`${mention.title ?? mention.url} (abre en una pestaña nueva)`}
							class="font-medium text-ink underline decoration-line underline-offset-[3px] hover:decoration-ink"
						>
							{mention.title ?? mention.url}
						</a>
						{#if mention.published_at}
							<time datetime={mention.published_at} class="ml-auto text-xs tabular-nums text-meta">
								{formatDisplayDateTime(mention.published_at)}
							</time>
						{/if}
					</li>
				{/each}
			</ul>
		{/if}
	</section>
{:catch cause}
	<div class="empty mt-4 border-danger/40" role="alert">
		<p class="font-medium text-danger">No se pudo cargar el evento.</p>
		<p class="mt-1">{cause?.message ?? 'Error desconocido'}</p>
	</div>
{/await}
