<script lang="ts">
	import { formatDisplayDateTime, sentimentLabel, sourceLabel } from '$lib/format';
	import { INPUT_CLS } from '$lib/ui';
	import type { PageProps } from './$types';

	let { form: result }: PageProps = $props();
</script>

<svelte:head>
	<title>Consultas | Media Monitor</title>
</svelte:head>

<div class="max-w-3xl">
	<h1 class="text-2xl font-semibold tracking-tight">Consultas</h1>
	<p class="mt-1 text-sm text-slate-500">
		Pregunta en lenguaje natural sobre la cobertura; la respuesta se apoya
		exclusivamente en las notas ingestadas, con citas.
	</p>

	<form method="POST" class="mt-6 flex flex-wrap items-start gap-2">
		<input
			type="text"
			name="question"
			value={result?.question ?? ''}
			placeholder="¿Qué ha dicho Lilia Cedillo sobre las becas?"
			aria-label="Pregunta"
			class={`min-w-0 flex-1 ${INPUT_CLS}`}
		/>
		<button
			type="submit"
			class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
		>
			Consultar
		</button>
	</form>

	{#if result?.error}
		<div class="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
			{result.error}
		</div>
	{/if}

	{#if result?.answer}
		<article class="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
			<h2 class="text-xs font-semibold uppercase tracking-wide text-slate-400">Respuesta</h2>
			<p class="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-800">
				{result.answer}
			</p>
			{#if result.matched_mentions}
				<p class="mt-3 text-xs text-slate-400">
					Contexto: {result.matched_mentions} notas
				</p>
			{/if}
		</article>
	{/if}

	{#if result?.citations && result.citations.length > 0}
		<h2 class="mt-6 text-xs font-semibold uppercase tracking-wide text-slate-400">Fuentes</h2>
		<ul class="mt-2 grid gap-2" aria-label="Fuentes de la respuesta">
			{#each result.citations as citation (citation.mention_id)}
				<li>
					<a
						href={citation.url}
						target="_blank"
						rel="noopener noreferrer"
						class="block rounded-lg border border-slate-200 bg-white px-4 py-2.5 text-sm shadow-sm hover:border-slate-300"
					>
						<span class="font-medium text-slate-800">{citation.title ?? citation.url}</span>
						<span class="ml-2 text-xs text-slate-400">
							{sourceLabel(citation.source)} ·
							{formatDisplayDateTime(citation.published_at)}
							{#if citation.sentiment}
								· {sentimentLabel(citation.sentiment)}
							{/if}
						</span>
					</a>
				</li>
			{/each}
		</ul>
	{/if}

	{#if result?.person}
		<p class="mt-4 text-xs text-slate-400">
			Pregunta vinculada a:
			<a href={`/persons/${result.person.id}`} class="underline hover:text-slate-600">
				{result.person.name}
			</a>
		</p>
	{/if}
</div>
