<script lang="ts">
	import { INPUT_CLS } from '$lib/ui';
	import { formatDisplayDateTime } from '$lib/format';
	import DigestSections from '$lib/components/DigestSections.svelte';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const summary = $derived(data.summary);
	const day = $derived(data.day);

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
		<h1 class="text-2xl font-semibold tracking-tight">Digest del día</h1>
		<p class="mt-1 text-sm text-slate-500">
			Resumen editorial: noticias por eje, rectora, redes y personas.
		</p>
	</div>

	<form method="POST" action="?/view" class="flex flex-wrap items-center gap-2">
		<input
			type="date"
			name="date"
			value={day}
			aria-label="Fecha del digest"
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
	<section aria-label="Titular del día" class="mt-6 rounded-xl border border-slate-200 bg-slate-900 p-6 text-white shadow-sm">
		<div class="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-slate-400">
			<span>{summary.summary_date}</span>
			<span
				class="rounded-full px-2 py-0.5 text-[11px] font-medium
				{summary.mode === 'llm' ? 'bg-emerald-500/20 text-emerald-300' : 'bg-slate-700 text-slate-300'}"
			>
				{modeLabel[summary.mode] ?? summary.mode}
			</span>
			<span class="normal-case text-slate-500">
				actualizado {formatDisplayDateTime(summary.updated_at)}
			</span>
		</div>
		<p class="mt-3 text-lg leading-relaxed">{summary.narrative}</p>
	</section>

	<div class="mt-6 grid gap-6 lg:grid-cols-3">
		<div class="min-w-0 lg:col-span-2">
			<DigestSections content={summary.content} />
		</div>

		<aside aria-label="Historial" class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
			<h2 class="text-sm font-semibold uppercase tracking-wide text-slate-500">Historial</h2>
			{#if data.days.length === 0}
				<p class="mt-2 text-sm text-slate-500">Todavía no hay digests guardados.</p>
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

	<details class="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
		<summary class="cursor-pointer text-sm font-medium text-slate-700">
		Texto plano (para el chat con RAG)
		</summary>
		<pre class="mt-3 whitespace-pre-wrap text-sm text-slate-600">{summary.content.plain_text}</pre>
	</details>
{:else}
	<div class="mt-10 rounded-xl border border-dashed border-slate-300 bg-slate-50 p-10 text-center">
		<p class="text-sm text-slate-500">
			No hay digest guardado para <span class="font-medium text-slate-700">{day}</span>.
		</p>
		<p class="mt-1 text-sm text-slate-400">Usá «Generar ahora» para construirlo.</p>
	</div>
{/if}
