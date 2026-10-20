<script lang="ts">
	import { goto } from '$app/navigation';

	import { formatDisplayDateTime, formatLongDate } from '$lib/format';
	import { monogram } from '$lib/digest-stats';
	import DigestSections from '$lib/components/DigestSections.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const summary = $derived(data.summary);
	const day = $derived(data.day);

	const modeLabel: Record<string, string> = {
		heuristic: 'Plantilla',
		llm: 'IA'
	};

	const governmentCount = $derived.by(() => {
		const byTopic = summary?.content.coverage?.by_topic;
		if (byTopic && 'government' in byTopic) return byTopic.government;
		return (
			summary?.content.noticias?.filter((item) => item.topic === 'government').length ?? 0
		);
	});
</script>

<svelte:head>
	<title>Resumen diario | Media Monitor</title>
</svelte:head>

<div class="grid gap-4 lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-4">
	<div class="min-w-0">
		{#if summary}
			<section class="digest-header" aria-labelledby="digest-date">
				<div class="eyebrow">Resumen diario / BUAP</div>
				<h1 id="digest-date">{formatLongDate(summary.summary_date)}</h1>
				<div class="digest-meta">
					<span class="mode">{modeLabel[summary.mode] ?? summary.mode}</span>
					<span>actualizado {formatDisplayDateTime(summary.updated_at)}</span>
				</div>
			</section>

			<section class="narrative" aria-labelledby="narrative-heading">
				<div class="eyebrow" id="narrative-heading">Resumen del día</div>
				<p>{summary.narrative}</p>
			</section>

			<DigestSections
				content={summary.content}
				tones={data.tones}
				updatedAt={summary.updated_at}
			/>

			<details class="panel">
				<summary class="cursor-pointer text-sm font-medium text-ink">
					Texto plano (para el chat con RAG)
				</summary>
				<pre class="mt-3 whitespace-pre-wrap text-sm text-ink-2">{summary.content.plain_text}</pre>
			</details>
		{:else}
			<div class="empty mt-6" role="status">
				<p>No hay digest guardado para <span class="font-medium text-ink">{day}</span>.</p>
				<p class="mt-1 text-muted">Se publica automáticamente en el horario configurado.</p>
			</div>
		{/if}
	</div>

	<aside class="sidebar digest-aside" aria-label="Seguimiento especial, archivo y actores">
		<section class="sidebar-section" aria-labelledby="archivo-heading">
			<h2 id="archivo-heading">Historial</h2>
			{#if data.days.length === 0}
				<p class="small-note">Todavía no hay resúmenes guardados.</p>
			{:else}
				<ul class="history-list">
					{#each data.days as entry (entry.summary_date)}
						<li>
							<button
								type="button"
								aria-label="Consultar resumen del {formatLongDate(entry.summary_date)}"
								aria-pressed={entry.summary_date === day}
								onclick={() => goto(`?date=${entry.summary_date}`)}
							>
								<span>{formatLongDate(entry.summary_date)}</span>
								<span class="mode">{modeLabel[entry.mode] ?? entry.mode}</span>
							</button>
						</li>
					{/each}
				</ul>
			{/if}
			<p class="small-note">La consulta histórica requiere conexión al backend.</p>
		</section>

		<section class="sidebar-section" aria-labelledby="actores-heading">
			<h2 id="actores-heading">Actores en seguimiento</h2>
			{#if data.persons.length === 0}
				<p class="small-note">Sin actores registrados todavía.</p>
			{:else}
				{#each data.persons as person (person.id)}
					<div class="actor-entry">
						<span class="actor-monogram" aria-hidden="true">{monogram(person.name)}</span>
						<div>
							<span class="actor-name">{person.name}</span>
							<span class="actor-role">
								{[person.role ?? person.org, `${person.mention_count} menciones`]
									.filter(Boolean)
									.join(' · ')}
							</span>
						</div>
					</div>
				{/each}
				<a class="actor-link" href="/persons">Ver cobertura →</a>
			{/if}
		</section>

		<section class="sidebar-section" aria-labelledby="especial-heading">
			<h2 id="especial-heading">Categorías en seguimiento especial</h2>
			<div class="special-topic">
				<span class="special-topic-name">Gobierno</span>
				<span class="special-topic-scope">Tema prioritario en noticias y redes sociales</span>
				<p class="special-topic-status">
					{governmentCount > 0
						? `${governmentCount} ${governmentCount === 1 ? 'nota clasificada' : 'notas clasificadas'} hoy.`
						: 'Sin notas clasificadas en esta categoría hoy.'}
				</p>
			</div>
		</section>

		<section class="sidebar-section" aria-labelledby="temas-heading">
			<h2 id="temas-heading">Temas en seguimiento</h2>
			{#if data.keywords.length === 0}
				<p class="tracked-topics-empty" role="status">
					Los temas definidos en Configuración aparecerán aquí.
				</p>
			{:else}
				<ul class="tracked-list">
					{#each data.keywords as keyword (keyword.id)}
						<li>{keyword.text}</li>
					{/each}
				</ul>
			{/if}
		</section>
	</aside>
</div>
