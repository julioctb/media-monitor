<script lang="ts">
	import type { PageProps } from './$types';

	import { INPUT_CLS } from '$lib/ui';
	import type { DailySummaryContent } from '$lib/api';

	let { data, form }: PageProps = $props();


	type Bucket = NonNullable<DailySummaryContent['per_source']>[string];
	const NO_BUCKETS: Record<string, Bucket> = {};

	const summary = $derived(data.summary);
	const day = $derived(data.day);

	const perSource = $derived(Object.entries(summary?.content.per_source ?? NO_BUCKETS));
	const keywordRows = $derived.by(() => {
		const mentioned = Object.entries(summary?.content.per_keyword ?? NO_BUCKETS).map(
			([name, info]) => ({
				name,
				count: info.count,
				topTitles: info.top_titles,
				silent: false
			})
		);
		const silent = (summary?.content.silent_keywords ?? []).map((name: string) => ({
			name,
			count: 0,
			topTitles: [] as string[],
			silent: true
		}));
		return [...mentioned, ...silent];
	});
	const totals = $derived(summary?.content.totals ?? {});

	/** Spanish labels for the totals row; unknown keys fall back to the raw key. */
	const TOTAL_LABELS: Record<string, string> = {
		sources: 'Fuentes',
		mentions: 'Menciones',
		keywords_with_mentions: 'Palabras con menciones',
		silent_keywords: 'Palabras sin menciones'
	};

	const modeLabel: Record<string, string> = {
		heuristic: 'Plantilla',
		llm: 'IA'
	};
</script>

<svelte:head>
	<title>Resumen diario | Media Monitor</title>
</svelte:head>

<div class="flex flex-wrap items-end justify-between gap-4">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">Resumen diario</h1>
		<p class="mt-1 text-sm text-slate-500">
			Digest de menciones por fuente y palabra clave, guardado un registro por día.
		</p>
	</div>

	<form method="POST" action="?/view" class="flex flex-wrap items-center gap-2">
		<input
			type="date"
			name="date"
			value={day}
			aria-label="Fecha del resumen"
			class={INPUT_CLS}
		/>
		<button
			type="submit"
			class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 shadow-sm hover:bg-slate-50"
		>
			Ver
		</button>
		<button
			type="submit"
			formaction="?/generate"
			class="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white shadow-sm hover:bg-slate-700"
		>
			Generar ahora
		</button>
	</form>
</div>

{#if form && !form.ok}
	<div role="alert" class="mt-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
		{form.message}
	</div>
{/if}

{#if summary}
	<section aria-label="Narrativa del día" class="mt-6 rounded-xl border border-slate-200 bg-slate-900 p-6 text-white shadow-sm">
		<div class="flex items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
			<span>{summary.summary_date}</span>
			<span
				class="rounded-full px-2 py-0.5 text-[11px] font-medium
				{summary.mode === 'llm' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-300'}"
			>
				{modeLabel[summary.mode] ?? summary.mode}
			</span>
		</div>
		<p class="mt-3 text-lg leading-relaxed">{summary.narrative}</p>
	</section>

	<div class="mt-6 grid gap-6 lg:grid-cols-3">
		<section aria-label="Por fuente" class="min-w-0 lg:col-span-2">
			<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Por fuente</h2>
			{#if perSource.length === 0}
				<p class="mt-2 text-sm text-slate-500">Sin menciones registradas ese día.</p>
			{:else}
				<div class="mt-3 grid gap-4 sm:grid-cols-2">
					{#each perSource as [source, info] (source)}
						<article class="min-w-0 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
							<header class="flex items-baseline justify-between">
								<h3 class="font-medium text-slate-900">{source}</h3>
								<span class="text-sm text-slate-500">{info.count}</span>
							</header>
							{#if info.top_titles.length > 0}
								<ul class="mt-2 space-y-1 text-sm text-slate-600">
									{#each info.top_titles as title (title)}
										<li class="truncate">«{title}»</li>
									{/each}
								</ul>
							{/if}
						</article>
					{/each}
				</div>
			{/if}
		</section>

		<aside aria-label="Historial" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
			<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Historial</h2>
			{#if data.days.length === 0}
				<p class="mt-2 text-sm text-slate-500">Todavía no hay resúmenes guardados.</p>
			{:else}
				<ul class="mt-3 space-y-1">
					{#each data.days as entry (entry.summary_date)}
						<li>
							<a
								href="?date={entry.summary_date}"
								class="flex items-center justify-between rounded-md px-2 py-1.5 text-sm
								{entry.summary_date === day ? 'bg-slate-900 text-white' : 'text-slate-700 hover:bg-slate-100'}"
							>
								<span>{entry.summary_date}</span>
								<span class="text-xs opacity-70">{modeLabel[entry.mode] ?? entry.mode}</span>
							</a>
						</li>
					{/each}
				</ul>
			{/if}
		</aside>
	</div>

	<section aria-label="Palabras clave" class="mt-6">
		<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Palabras clave</h2>
		{#if keywordRows.length === 0}
			<p class="mt-2 text-sm text-slate-500">Sin palabras clave configuradas.</p>
		{:else}
			<ul class="mt-3 flex flex-wrap gap-2">
				{#each keywordRows as row (row.name)}
					<li
						class="rounded-full border px-3 py-1 text-sm
						{row.silent
							? 'border-dashed border-slate-300 bg-slate-50 text-slate-400'
							: 'border-slate-300 bg-white text-slate-700'}"
					>
						{row.name}
						<span class="ml-1 text-xs">{row.silent ? 'sin menciones' : row.count}</span>
					</li>
				{/each}
			</ul>
		{/if}
	</section>

	<section aria-label="Totales" class="mt-6 grid grid-cols-2 gap-4 sm:grid-cols-4">
		{#each Object.entries(totals) as [key, value] (key)}
			<div class="rounded-xl border border-slate-200 bg-white p-4 text-center shadow-sm">
				<div class="text-2xl font-semibold text-slate-900">{value}</div>
				<div class="text-xs uppercase tracking-wide text-slate-500">
					{TOTAL_LABELS[key] ?? key.replaceAll('_', ' ')}
				</div>
			</div>
		{/each}
	</section>

	<details class="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
		<summary class="cursor-pointer text-sm font-medium text-slate-700">
		Texto plano (para el chat con RAG)
		</summary>
		<pre class="mt-3 whitespace-pre-wrap text-sm text-slate-600">{summary.content.plain_text}</pre>
	</details>
{:else}
	<div class="mt-10 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
		<p class="text-sm text-slate-500">
			No hay resumen guardado para <span class="font-medium text-slate-700">{day}</span>.
		</p>
		<p class="mt-1 text-sm text-slate-400">Usá «Generar ahora» para construirlo.</p>
	</div>
{/if}
