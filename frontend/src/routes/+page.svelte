<script lang="ts">
	import { BTN_GHOST_CLS, BTN_PRIMARY_CLS, INPUT_CLS } from '$lib/ui';
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

<header class="flex flex-wrap items-end justify-between gap-4">
	<div>
		<h1 class="page-title">Digest del día</h1>
		<p class="lead">Resumen editorial: noticias por eje, rectora, redes y personas.</p>
	</div>

	<form method="POST" action="?/view" class="flex flex-wrap items-center gap-2">
		<input
			type="date"
			name="date"
			value={day}
			aria-label="Fecha del digest"
			class={INPUT_CLS}
		/>
		<button type="submit" class={BTN_GHOST_CLS}>Ver</button>
		<button type="submit" formaction="?/generate" class={BTN_PRIMARY_CLS}>Generar ahora</button>
	</form>
</header>

{#if form && !form.ok}
	<div role="alert" class="empty mt-4 border-danger/40">
		{form.message}
	</div>
{/if}

{#if summary}
	<section aria-label="Titular del día" class="mt-6 rounded-2xl bg-ink p-6 text-white">
		<div class="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-white/60">
			<span>{summary.summary_date}</span>
			<span
				class="rounded-full px-2 py-0.5 text-[11px] font-medium
				{summary.mode === 'llm' ? 'bg-accent text-white' : 'bg-white/15 text-white/80'}"
			>
				{modeLabel[summary.mode] ?? summary.mode}
			</span>
			<span class="normal-case text-white/50">
				actualizado {formatDisplayDateTime(summary.updated_at)}
			</span>
		</div>
		<p class="mt-3 text-lg leading-relaxed">{summary.narrative}</p>
	</section>

	<div class="mt-6 grid gap-6 lg:grid-cols-[1fr_320px]">
		<div class="min-w-0">
			<DigestSections content={summary.content} />
		</div>

		<aside aria-label="Historial" class="self-start rounded-2xl border border-line-soft bg-white p-5">
			<h2 class="panel-title">Historial</h2>
			{#if data.days.length === 0}
				<p class="mt-2 text-sm text-muted">Todavía no hay digests guardados.</p>
			{:else}
				<ul class="mt-3 space-y-1">
					{#each data.days as entry (entry.summary_date)}
						<li>
							<a
								href="?date={entry.summary_date}"
								class="flex items-center justify-between rounded-lg px-2 py-1.5 text-sm transition-colors
								{entry.summary_date === day ? 'bg-ink text-white' : 'text-ink-2 hover:bg-surface'}"
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

	<details class="mt-4 rounded-2xl border border-line-soft bg-white p-5">
		<summary class="cursor-pointer text-sm font-medium text-ink">
		Texto plano (para el chat con RAG)
		</summary>
		<pre class="mt-3 whitespace-pre-wrap text-sm text-ink-2">{summary.content.plain_text}</pre>
	</details>
{:else}
	<div class="empty mt-6" role="status">
		<p>
			No hay digest guardado para <span class="font-medium text-ink">{day}</span>.
		</p>
		<p class="mt-1 text-muted">Usá «Generar ahora» para construirlo.</p>
	</div>
{/if}
