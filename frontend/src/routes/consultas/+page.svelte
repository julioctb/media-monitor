<script lang="ts">
	import { formatDisplayDateTime, sentimentLabel, sourceLabel } from '$lib/format';
	import { BTN_PRIMARY_CLS, INPUT_CLS } from '$lib/ui';
	import type { PageProps } from './$types';

	let { form: result }: PageProps = $props();
</script>

<svelte:head>
	<title>Consultas | Media Monitor</title>
</svelte:head>

<header>
	<h1 class="page-title">Consultas</h1>
	<p class="lead">
		Pregunta en lenguaje natural sobre la cobertura; la respuesta se apoya
		exclusivamente en las notas ingestadas, con citas.
	</p>
</header>

<section class="panel mt-6" aria-labelledby="consultas-chat-title">
	<div class="panel-head">
		<h2 class="panel-title" id="consultas-chat-title">Nueva consulta</h2>
		<p class="panel-note">
			Las respuestas se generan solo con notas ingestadas y muestran sus citas.
		</p>
	</div>

	{#if result?.error}
		<div class="empty mt-4 border-warn/40" role="alert">
			{result.error}
		</div>
	{/if}

	<div class="mt-4" aria-live="polite">
		{#if result?.answer}
			{#if result.question}
				<div class="flex justify-end">
					<p class="max-w-[85%] rounded-2xl bg-ink px-4 py-2.5 text-sm text-white">
						{result.question}
					</p>
				</div>
			{/if}
			<div class="mt-3 rounded-2xl border border-line-soft bg-surface-warm p-5">
				<h3 class="text-xs font-bold uppercase tracking-wide text-meta">Respuesta</h3>
				<p class="mt-2 whitespace-pre-line text-sm leading-relaxed text-ink-2">
					{result.answer}
				</p>
				{#if result.matched_mentions}
					<p class="mt-3 text-xs text-meta">
						Fuentes citadas: {result.matched_mentions} nota{result.matched_mentions === 1 ? '' : 's'}
					</p>
				{/if}
			</div>
		{:else if !result?.error}
			<div class="rounded-2xl border border-dashed border-line bg-surface-warm p-8 text-center">
				<p class="text-base font-semibold text-ink">Explora la cobertura</p>
				<p class="mt-1 text-sm text-muted">
					Haz una pregunta sobre las notas registradas. La respuesta debe incluir citas
					verificables.
				</p>
			</div>
		{/if}
	</div>

	<form method="POST" class="mt-4 flex flex-wrap items-center gap-2">
		<input
			type="text"
			name="question"
			value={result?.question ?? ''}
			placeholder="¿Qué ha dicho Lilia Cedillo sobre las becas?"
			aria-label="Pregunta"
			class={`min-w-0 flex-1 ${INPUT_CLS}`}
		/>
		<button type="submit" class={BTN_PRIMARY_CLS}>Consultar</button>
	</form>
</section>

{#if result?.citations && result.citations.length > 0}
	<section class="panel mt-4" aria-labelledby="consultas-sources-title">
		<div class="panel-head">
			<h2 class="panel-title" id="consultas-sources-title">Fuentes</h2>
			<p class="panel-note">Notas que sustentan la respuesta.</p>
		</div>
		<ul class="mt-4 grid gap-2" aria-label="Fuentes de la respuesta">
			{#each result.citations as citation (citation.mention_id)}
				<li>
					<a
						href={citation.url}
						target="_blank"
						rel="noopener noreferrer"
						class="block rounded-xl border border-line-soft bg-white px-4 py-2.5 text-sm transition-colors hover:border-line"
					>
						<span class="font-medium text-ink underline decoration-line underline-offset-[3px] hover:decoration-ink"
							>{citation.title ?? citation.url}</span
						>
						<span class="ml-2 text-xs text-meta">
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
	</section>
{/if}

{#if result?.person}
	<p class="footnote">
		Pregunta vinculada a:
		<a href={`/persons/${result.person.id}`} class="underline hover:text-ink">
			{result.person.name}
		</a>
	</p>
{/if}
