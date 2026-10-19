<script lang="ts">
	import { sourceLabel, topicLabel } from '$lib/format';

	import type { DailySummaryContent } from '$lib/api';

	let { content }: { content: DailySummaryContent } = $props();

	const noticias = $derived(content.noticias ?? []);
	const rectora = $derived(content.rectora ?? {});
	const redes = $derived(Object.entries(content.redes ?? {}));
	const personas = $derived(content.personas ?? []);
	const pendientes = $derived(content.pendientes ?? []);
	const gaps = $derived(content.coverage?.gaps ?? []);

	/** Confidence badge palette; unknown values stay quiet gray. */
	const CONFIDENCE_CLS: Record<string, string> = {
		alta: 'bg-success/10 text-success ring-success/30',
		media: 'bg-warn/15 text-warn ring-warn/30',
		baja: 'bg-surface text-muted ring-line'
	};
</script>

<section aria-label="Noticias del día" class="panel min-w-0">
	<div class="panel-head">
		<h2 class="panel-title">Noticias</h2>
	</div>
	{#if noticias.length === 0}
		<p class="mt-3 text-sm text-muted">Sin noticias registradas ese día.</p>
	{:else}
		<ul class="mt-4 space-y-3">
			{#each noticias as item, i (item.event_id ?? `i${i}`)}
				<li class="rounded-xl border border-line-soft bg-surface-warm p-4">
					<div class="flex flex-wrap items-center gap-2">
						{#if item.topic}
							<span class="rounded-full border border-line-soft bg-surface px-2.5 py-0.5 text-[11px] font-medium text-ink-2">
								{topicLabel(item.topic)}
							</span>
						{/if}
						{#if item.confidence}
							<span
								class="rounded-full px-2 py-0.5 text-[11px] font-medium ring-1
								{CONFIDENCE_CLS[item.confidence] ?? 'bg-surface text-muted ring-line'}"
							>
								Confianza {item.confidence}
							</span>
						{/if}
					</div>
					<h3 class="mt-2 text-sm font-semibold text-ink">{item.title}</h3>
					{#if item.summary}
						<p class="mt-1 text-sm text-ink-2">{item.summary}</p>
					{/if}
					{#if item.why_it_matters}
						<p class="mt-1 text-sm italic text-muted">Por qué importa: {item.why_it_matters}</p>
					{/if}
					{#if item.sources.length > 0}
						<p class="mt-2 text-xs text-meta">
							Fuentes:
							{item.sources.map((s) => sourceLabel(s.source)).join(' · ')}
						</p>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<section aria-label="Rectora" class="panel">
	<div class="panel-head">
		<h2 class="panel-title">Rectora</h2>
	</div>
	<div class="mt-4">
		{#if rectora.mention_count}
			<ul class="space-y-1 text-sm text-ink-2">
				{#each rectora.actions ?? [] as action, i (i)}
					<li>«{action.title}»</li>
				{/each}
			</ul>
			<div class="mt-2 flex flex-wrap gap-3 text-xs text-muted">
				{#if rectora.tone}<span>Tono: {rectora.tone}</span>{/if}
				{#if rectora.watch}<span>Vigilar: {rectora.watch}</span>{/if}
			</div>
		{:else}
			<p class="text-sm text-muted">Sin menciones de la persona focal en la ventana.</p>
		{/if}
		{#if rectora.gaps}
			<p class="mt-1 text-xs text-meta">Gap: {rectora.gaps}</p>
		{/if}
	</div>
</section>

<section aria-label="Redes sociales" class="panel">
	<div class="panel-head">
		<h2 class="panel-title">Redes sociales</h2>
	</div>
	<ul class="mt-4 flex flex-wrap gap-2">
		{#each redes as [source, info] (source)}
			<li
				class="rounded-full border px-3 py-1 text-sm transition-colors
				{info.count === 0
					? 'border-dashed border-line bg-surface text-meta'
					: 'border-line bg-white text-ink-2'}"
			>
				{sourceLabel(source)}
				<span class="ml-1 text-xs">{info.count === 0 ? 'sin menciones' : info.count}</span>
			</li>
		{/each}
	</ul>
	{#if gaps.length > 0}
		<ul class="mt-2 space-y-0.5 text-xs text-meta">
			{#each gaps as gap (gap)}
				<li>{gap}</li>
			{/each}
		</ul>
	{/if}
</section>

<section aria-label="Personas mencionadas" class="panel">
	<div class="panel-head">
		<h2 class="panel-title">Personas mencionadas</h2>
	</div>
	{#if personas.length === 0}
		<p class="mt-3 text-sm text-muted">Sin personas detectadas ese día.</p>
	{:else}
		<ul class="mt-4 space-y-1">
			{#each personas as person (person.person_id)}
				<li class="text-sm text-ink-2">
					<a
						href={`/persons/${person.person_id}`}
						class="font-medium text-accent underline decoration-line underline-offset-[3px] hover:decoration-accent"
					>
						{person.name}
					</a>
					{#if person.role || person.org}
						<span class="text-xs text-meta">
							{[person.role, person.org].filter(Boolean).join(' · ')}
						</span>
					{/if}
					{#if person.fact}
						— {person.fact}
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

{#if pendientes.length > 0}
	<section aria-label="Pendientes" class="panel">
		<div class="panel-head">
			<h2 class="panel-title">Pendientes</h2>
		</div>
		<ul class="mt-3 list-disc space-y-0.5 pl-5 text-sm text-muted">
			{#each pendientes as pending (pending)}
				<li>{pending}</li>
			{/each}
		</ul>
	</section>
{/if}
