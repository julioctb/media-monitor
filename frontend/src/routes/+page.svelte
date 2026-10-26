<script lang="ts">
	import { invalidateAll, goto } from '$app/navigation';
	import { onMount } from 'svelte';

	import {
		formatDisplayDateTime,
		formatDisplayTime,
		formatLongDate,
		nextCutLabel
	} from '$lib/format';
	import { categoryRows, monogram } from '$lib/digest-stats';
	import DigestSections from '$lib/components/DigestSections.svelte';
	import DigestV3 from '$lib/components/DigestV3.svelte';
	import DigestEvidence from '$lib/components/DigestEvidence.svelte';
	import { createEvidenceContext } from '$lib/digest-evidence';
	import { digestV3View } from '$lib/digest-v3';
	import NegativeNews from '$lib/components/NegativeNews.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const summary = $derived(data.summary);
  const evidenceContext = $derived(createEvidenceContext(summary?.content));
	const day = $derived(data.day);

	// Auto-refresh while visible (same contract as the feed): picks up new
	// digest cuts and live counts without a manual reload. The digest's news
	// detail is frozen per cut; the day link in the negative panel hands off
	// to the live feed for anything newer.
	const REFRESH_MS = 90_000;
	let refreshTimer: ReturnType<typeof setInterval> | undefined = $state();
	let lastRefresh = $state<string | null>(null);

	function startAutoRefresh() {
		stopAutoRefresh();
		refreshTimer = setInterval(() => {
			if (document.visibilityState !== 'visible') return;
			void refreshNow();
		}, REFRESH_MS);
	}

	function stopAutoRefresh() {
		if (refreshTimer) clearInterval(refreshTimer);
		refreshTimer = undefined;
	}

	/** Hidden tabs skip the timer; the moment the tab is back, refresh. */
	function onVisibilityChange() {
		if (document.visibilityState === 'visible') void refreshNow();
	}

	async function refreshNow() {
		await invalidateAll();
		lastRefresh = new Date().toLocaleTimeString('es-MX', {
			hour: '2-digit',
			minute: '2-digit'
		});
	}

	onMount(() => {
		startAutoRefresh();
		document.addEventListener('visibilitychange', onVisibilityChange);
		return () => {
			stopAutoRefresh();
			document.removeEventListener('visibilitychange', onVisibilityChange);
		};
	});

	const updatedLabel = $derived(summary ? formatDisplayTime(summary.updated_at) : null);

	/** digest-brief-v3: the brief headline replaces the plain narrative (same text, promoted). */
	const v3Headline = $derived(
		summary ? (digestV3View(summary.content)?.headline ?? null) : null
	);
	const nextCut = $derived(nextCutLabel(data.digestHours, new Date()));

	/** Header eyebrow: «Resumen diario /» + active keywords (BUAP fallback). */
	const eyebrow = $derived.by(() => {
		const terms = data.keywords.filter((keyword) => keyword.is_active).map((k) => k.text);
		return terms.length > 0 ? `Resumen diario / ${terms.join(' · ')}` : 'Resumen diario / BUAP';
	});

	/** Categorías identificadas: top 5 shares over the day's real total. */
	const categoryRowsTop = $derived(
		categoryRows(data.liveCoverage?.byTopic, data.liveCoverage?.total).slice(0, 5)
	);
	const TOPIC_TOTAL = 9;
	const activeTopics = $derived(data.liveCoverage ? Object.keys(data.liveCoverage.byTopic).length : 0);

	/** Por término de búsqueda: active keywords crossed with the day counts. */
	const keywordRows = $derived.by(() => {
		const counts = new Map(data.keywordCounts.map((row) => [row.id, row.count]));
		return data.keywords.map((keyword) => ({ ...keyword, count: counts.get(keyword.id) ?? 0 }));
	});

	const coverageTotal = $derived(data.liveCoverage?.total ?? null);
	const liveEvents = $derived(data.liveCoverage?.events ?? null);

	/** Archive pagination: one month back per click, anchored on the visible page. */
	const olderHref = $derived(
		data.olderBefore
			? `?date=${encodeURIComponent(day)}&before=${encodeURIComponent(data.olderBefore)}`
			: null
	);
</script>

<svelte:head>
	<title>Resumen diario | Media Monitor</title>
</svelte:head>

<div class="digest-layout">
	<div class="digest-content">
		<!-- The page skeleton renders with or without a digest: a day
		    awaiting its first cut keeps the v2 structure in place under
		    placeholder states instead of collapsing to one legend. -->
		<section class="digest-header" aria-labelledby="digest-date">
			<div class="eyebrow">{eyebrow}</div>
			<h1 id="digest-date">{formatLongDate(summary?.summary_date ?? day)}</h1>
			<div class="digest-meta">
				{#if summary}
					<span>
						Interpretación actualizada a las {updatedLabel}{nextCut
							? ` · siguiente actualización a las ${nextCut}`
							: ''}
					</span>
				{:else}
					<span>En espera del primer corte del día</span>
					<span>
						Última actualización:
						{data.latest_updated_at ? formatDisplayDateTime(data.latest_updated_at) : '—'}
					</span>
				{/if}
				{#if lastRefresh}
					<span>refrescado {lastRefresh}</span>
				{/if}
			</div>
			{#if data.days.length > 1}
				<!-- Mobile day jump: the sidebar Historial sits below the whole
					digest on narrow viewports; this keeps day switching at hand. -->
				<div class="day-jump">
					<label class="day-jump-label" for="day-jump">Consultar otro día</label>
					<select
						id="day-jump"
						value={day}
						onchange={(event) => goto(`?date=${event.currentTarget.value}`)}
					>
						{#each data.days as entry (entry.summary_date)}
							<option value={entry.summary_date}>
								{formatLongDate(entry.summary_date)}
							</option>
						{/each}
					</select>
				</div>
			{/if}
		</section>

		<!-- digest-brief-v3: brief + evidencia + campo; renders nothing on legacy rows. -->
		<DigestV3 content={summary?.content ?? {}} context={evidenceContext} narrative={summary?.narrative} />

		{#if !v3Headline}
			<section class="narrative" aria-labelledby="narrative-heading">
				<div class="eyebrow" id="narrative-heading">Sintesis del día</div>
				{#if summary}
					<p>{summary.narrative}</p>
          {#if summary.narrative}<DigestEvidence context={evidenceContext} request={{ target: summary.content, field: 'headline', text: summary.narrative }} />{/if}
				{:else}
					<p>En espera de generar el resumen del día</p>
				{/if}
			</section>
		{/if}

		<NegativeNews mentions={data.negativeEvents} />

		<DigestSections
      context={evidenceContext}
			content={summary?.content ?? {}}
			tones={data.tones}
			sourcesCount={data.sourcesCount}
			socialLabels={data.socialLabels}
			negativeEvents={data.negativeEvents}
		/>
	</div>

	<aside class="sidebar digest-aside" aria-label="Historial, categorías y cobertura del día">
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
							</button>
						</li>
					{/each}
				</ul>
				{#if olderHref}
					<p class="small-note">
						<a class="month-link" href={olderHref}>ver mes anterior -&gt;</a>
					</p>
				{/if}
			{/if}
		</section>

		{#if categoryRowsTop.length > 0}
			<section class="sidebar-section" aria-labelledby="categorias-heading">
				<h2 id="categorias-heading">Categorías identificadas</h2>
				<p class="archive-copy">
					Distribución de las {coverageTotal}
					{coverageTotal === 1 ? 'nota' : 'notas'} del día.
				</p>
				<dl class="tone-list identified" aria-label="Porcentaje de noticias por categoría">
					{#each categoryRowsTop as row (row.key)}
						<div>
							<dt>{row.label}</dt>
							<dd>
								<span class="category-value">{row.pct}&nbsp;%</span>
								<span class="category-track" aria-hidden="true">
									<span class="category-fill" style="width:{row.pct}%"></span>
								</span>
							</dd>
						</div>
					{/each}
				</dl>
			</section>
		{/if}

		{#if data.persons.length > 0}
			<section class="sidebar-section persons-panel" aria-labelledby="personas-heading">
				<h2 id="personas-heading">Personas mencionadas</h2>
				{#each data.persons as person (person.id)}
					<div class="person-entry">
						<span class="person-monogram" aria-hidden="true">{monogram(person.name)}</span>
						<div class="person-data">
							<!-- The name is the link: no separate «ver cobertura» CTA. -->
							<a class="person-link" href="/persons/{person.id}">{person.name}</a>
							<p>
								{[person.role ?? person.org, `${person.mention_count} menciones`]
									.filter(Boolean)
									.join(' · ')}
							</p>
						</div>
					</div>
				{/each}
			</section>
		{/if}

		<section class="sidebar-section" aria-labelledby="cobertura-dia-heading">
			<h2 id="cobertura-dia-heading">Cobertura del día</h2>
			<p class="coverage-figure">
				<strong>{coverageTotal ?? '—'}</strong>
				<span>
					{coverageTotal === 1 ? 'nota registrada en la jornada' : 'notas registradas en la jornada'}
				</span>
			</p>
			<dl class="coverage-rows">
				<div>
					<dt>Categorías</dt>
					<dd>{activeTopics} de {TOPIC_TOTAL}</dd>
				</div>
				<div>
					<dt>Eventos creados</dt>
					<dd>{liveEvents ?? '—'}</dd>
				</div>
			</dl>
			{#if keywordRows.length > 0}
				<div class="day-terms">
					<h3>Por término de búsqueda</h3>
					<dl class="day-terms-list">
						{#each keywordRows as row (row.id)}
							<div>
								<dt>{row.text}</dt>
								<dd>{row.count}</dd>
							</div>
						{/each}
					</dl>
				</div>
			{/if}
		</section>
	</aside>
</div>
