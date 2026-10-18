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
		alta: 'bg-emerald-50 text-emerald-700 ring-emerald-200',
		media: 'bg-amber-50 text-amber-700 ring-amber-200',
		baja: 'bg-slate-100 text-slate-500 ring-slate-200'
	};
</script>

<section aria-label="Noticias del día" class="min-w-0">
	<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Noticias</h2>
	{#if noticias.length === 0}
		<p class="mt-2 text-sm text-slate-500">Sin noticias registradas ese día.</p>
	{:else}
		<ul class="mt-3 space-y-3">
			{#each noticias as item, i (item.event_id ?? `i${i}`)}
				<li class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
					<div class="flex flex-wrap items-center gap-2">
						{#if item.topic}
							<span class="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] font-medium text-slate-600">
								{topicLabel(item.topic)}
							</span>
						{/if}
						{#if item.confidence}
							<span
								class="rounded-full px-2 py-0.5 text-[11px] font-medium ring-1
								{CONFIDENCE_CLS[item.confidence] ?? 'bg-slate-100 text-slate-500 ring-slate-200'}"
							>
								Confianza {item.confidence}
							</span>
						{/if}
					</div>
					<h3 class="mt-2 text-sm font-semibold text-slate-900">{item.title}</h3>
					{#if item.summary}
						<p class="mt-1 text-sm text-slate-600">{item.summary}</p>
					{/if}
					{#if item.why_it_matters}
						<p class="mt-1 text-sm italic text-slate-500">Por qué importa: {item.why_it_matters}</p>
					{/if}
					{#if item.sources.length > 0}
						<p class="mt-2 text-xs text-slate-400">
							Fuentes:
							{item.sources.map((s) => sourceLabel(s.source)).join(' · ')}
						</p>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>

<section aria-label="Rectora" class="mt-6">
	<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Rectora</h2>
	<div class="mt-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
		{#if rectora.mention_count}
			<ul class="space-y-1 text-sm text-slate-700">
				{#each rectora.actions ?? [] as action, i (i)}
					<li>«{action.title}»</li>
				{/each}
			</ul>
			<div class="mt-2 flex flex-wrap gap-3 text-xs text-slate-500">
				{#if rectora.tone}<span>Tono: {rectora.tone}</span>{/if}
				{#if rectora.watch}<span>Vigilar: {rectora.watch}</span>{/if}
			</div>
		{:else}
			<p class="text-sm text-slate-500">Sin menciones de la persona focal en la ventana.</p>
		{/if}
		{#if rectora.gaps}
			<p class="mt-1 text-xs text-slate-400">Gap: {rectora.gaps}</p>
		{/if}
	</div>
</section>

<section aria-label="Redes sociales" class="mt-6">
	<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Redes sociales</h2>
	<ul class="mt-3 flex flex-wrap gap-2">
		{#each redes as [source, info] (source)}
			<li
				class="rounded-full border px-3 py-1 text-sm
				{info.count === 0
					? 'border-dashed border-slate-300 bg-slate-50 text-slate-400'
					: 'border-slate-300 bg-white text-slate-700'}"
			>
				{sourceLabel(source)}
				<span class="ml-1 text-xs">{info.count === 0 ? 'sin menciones' : info.count}</span>
			</li>
		{/each}
	</ul>
	{#if gaps.length > 0}
		<ul class="mt-2 space-y-0.5 text-xs text-slate-400">
			{#each gaps as gap (gap)}
				<li>{gap}</li>
			{/each}
		</ul>
	{/if}
</section>

<section aria-label="Personas mencionadas" class="mt-6">
	<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Personas mencionadas</h2>
	{#if personas.length === 0}
		<p class="mt-2 text-sm text-slate-500">Sin personas detectadas ese día.</p>
	{:else}
		<ul class="mt-3 space-y-1">
			{#each personas as person (person.person_id)}
				<li class="text-sm text-slate-700">
					<a href={`/persons/${person.person_id}`} class="font-medium hover:underline">
						{person.name}
					</a>
					{#if person.role || person.org}
						<span class="text-xs text-slate-400">
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
	<section aria-label="Pendientes" class="mt-6">
		<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Pendientes</h2>
		<ul class="mt-2 list-disc space-y-0.5 pl-5 text-sm text-slate-500">
			{#each pendientes as pending (pending)}
				<li>{pending}</li>
			{/each}
		</ul>
	</section>
{/if}
