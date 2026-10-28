<script lang="ts">
	import { invalidateAll, goto } from '$app/navigation';
	import { onMount } from 'svelte';

	import {
		calendarParts,
		formatDisplayDateTime,
		formatDisplayTime,
		formatLongDate,
		nextCutLabel
	} from '$lib/format';
	import { categoryRows } from '$lib/digest-stats';
	import DigestSections from '$lib/components/DigestSections.svelte';
	import DigestEvidence from '$lib/components/DigestEvidence.svelte';
	import TarjetaCard from '$lib/components/TarjetaCard.svelte';
	import { createEvidenceContext } from '$lib/digest-evidence';
	import { digestV3View, type BriefEntryView } from '$lib/digest-v3';
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

	const nextCut = $derived(nextCutLabel(data.digestHours, new Date()));

	/** Daily-structure eyebrow: «Resumen diario /» + active keywords (BUAP fallback). */
	const eyebrow = $derived.by(() => {
		const terms = data.keywords.filter((keyword) => keyword.is_active).map((k) => k.text);
		return terms.length > 0 ? `Resumen diario / ${terms.join(' · ')}` : 'Resumen diario / BUAP';
	});

	// Daily structure (mockup daily-view): one view model feeds every panel.
	// Legacy v2 rows yield null and only the synthesis/detail surfaces render.
	const view = $derived(summary ? digestV3View(summary.content) : null);

	/** Síntesis lead: the narrative prose, else the brief headline (same
	 * promotion rule the brief panel used). */
	const lead = $derived(summary ? (summary.narrative?.trim() || view?.headline || null) : null);

	const headlineRequest = $derived(
		summary
			? { target: summary.content as unknown, field: 'headline', text: lead }
			: undefined
	);

	/** Evidence request for a brief-entry field (mirror of the brief panel). */
	function entryEvidence(entry: BriefEntryView, field: string) {
		return { target: entry.raw, field, allowed: entry.sourceRefs ?? null };
	}

	/** Attention picks in brief order, each carrying its section label. */
	const PICK_LABELS = [
		{ key: 'riesgos', label: 'Riesgo' },
		{ key: 'decisiones', label: 'Decisión / atención' },
		{ key: 'aFavor', label: 'A favor' },
		{ key: 'ruido', label: 'Ruido' }
	] as const;

	type AttentionPick = BriefEntryView & { category: string };

	const picks = $derived.by(() => {
		if (!view) return [] as AttentionPick[];
		const result: AttentionPick[] = [];
		for (const { key, label } of PICK_LABELS) {
			for (const entry of view[key]) result.push({ ...entry, category: label });
		}
		return result;
	});

	/** Mockup's parallel «Decisiones y acciones sugeridas»: picks with an action. */
	const acciones = $derived(picks.filter((pick) => pick.accionSugerida || pick.condicion));

	const tarjetas = $derived(
		view?.tarjetas.filter(
			(tarjeta) => tarjeta.titulo || tarjeta.hecho || tarjeta.porQue || tarjeta.anguloNuevo || tarjeta.notas?.length
		) ?? []
	);

	const calendar = $derived(calendarParts(day));

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

<div class="daily-page">
	<h1 class="sr-only">Resumen diario</h1>

	<!-- Mockup daily-summary-row: editorial synthesis + date/cut control. -->
	<div class="daily-summary-row">
		<section class="daily-synthesis" aria-labelledby="daily-synthesis-title">
			<div class="daily-synthesis-heading">
				<h2 id="daily-synthesis-title">Síntesis del día</h2>
				<span>{eyebrow}</span>
			</div>
			<div class="daily-synthesis-copy">
				{#if summary}
					{#if lead}
							<p class="daily-synthesis-lead">{lead}</p>
							<DigestEvidence context={evidenceContext} request={headlineRequest} />
						{/if}
				{:else}
					<p class="daily-synthesis-lead">En espera de generar el resumen del día</p>
				{/if}
			</div>
			{#if lastRefresh}
				<p class="daily-synthesis-context">Refrescado a las {lastRefresh}.</p>
			{/if}
		</section>

		<div class="daily-selection">
			<div class="daily-date-control">
				<span class="briefing-date-kicker">Fecha del informe</span>
				{#if calendar}
					<time class="briefing-calendar" datetime={day} aria-label={formatLongDate(day)}>
						<span class="briefing-weekday">{calendar.weekday}</span>
						<span class="briefing-day">{calendar.day}</span>
						<span class="briefing-month">{calendar.monthYear}</span>
					</time>
				{/if}
				<span class="briefing-cutoff">
					{#if summary}
						Actualizado a las {updatedLabel}
						{#if nextCut}<span>Siguiente actualización a las {nextCut}</span>{/if}
					{:else}
						En espera del primer corte del día
						<span>
							Última actualización:
							{data.latest_updated_at ? formatDisplayDateTime(data.latest_updated_at) : '—'}
						</span>
					{/if}
				</span>
				{#if data.days.length > 0}
					<div class="briefing-date-picker">
						<label for="day-jump">Consultar otro día</label>
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
						{#if olderHref}
							<a class="text-link" href={olderHref}>ver mes anterior</a>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	</div>

	{#if picks.length > 0}
		<!-- Mockup executive block: the brief's picks as attention cards. -->
		<div class="executive-heading">
			<h2>Qué requiere atención</h2>
			<span class="executive-note">Selección editorial del día, no volumen de publicaciones.</span>
		</div>
		<div class="executive-priorities">
			{#each picks as pick, i (`${pick.category}-${i}`)}
				<article class="panel executive-priority">
					<div class="executive-card-top">
						<span class="daily-number">{String(i + 1).padStart(2, '0')}</span>
						<span class="source-badge">{pick.category}</span>
					</div>
					<h3>{pick.titulo}</h3>
					{#if pick.razon}<p class="executive-reason">{pick.razon}</p>{/if}
					{#if pick.afectacion}
						<dl class="executive-facts">
							<div>
								<dt>Afectación</dt>
								<dd>{pick.afectacion}</dd>
							</div>
						</dl>
					{/if}
					{#if pick.razon}
						<div class="executive-evidence">
							<DigestEvidence
								context={evidenceContext}
								request={entryEvidence(pick, 'razon')}
							/>
						</div>
					{/if}
				</article>
			{/each}
		</div>
		{#if view?.descarte}
			<p class="daily-brief-note">{view.descarte}</p>
		{/if}
	{/if}

	<!-- Mockup daily-layout: actions/changes/people main column + agenda/coverage side. -->
	<div class="daily-layout executive-support">
		<div class="daily-main">
			{#if view}
				<section class="panel executive-actions" aria-labelledby="executive-actions-heading">
					<h2 id="executive-actions-heading">Decisiones y acciones sugeridas</h2>
					<p>Propuestas de seguimiento, no decisiones aprobadas ni verificación de hechos.</p>
					{#if acciones.length > 0}
						{#each acciones as pick, i (`accion-${i}`)}
							<article class="executive-action">
								<h3>{pick.titulo}</h3>
								{#if pick.accionSugerida}
									<p>{pick.accionSugerida}</p>
									<DigestEvidence
										context={evidenceContext}
										request={entryEvidence(pick, 'accion_sugerida')}
									/>
								{/if}
								<dl class="executive-action-meta">
									{#if pick.condicion}
										<div>
											<dt>Condición para actuar</dt>
											<dd>{pick.condicion}</dd>
										</div>
									{/if}
									<div>
										<dt>Plazo documentado</dt>
										<dd>No consta un plazo en los registros.</dd>
									</div>
								</dl>
								{#if pick.condicion}
									<DigestEvidence
										context={evidenceContext}
										request={entryEvidence(pick, 'condicion')}
									/>
								{/if}
							</article>
						{/each}
					{:else}
						<p class="daily-empty-note">Sin acciones sugeridas en el corte de este día.</p>
					{/if}
				</section>
			{/if}

			{#if view && view.delta.length > 0}
				<section class="panel daily-side-panel daily-changes" aria-labelledby="daily-changes-heading">
					<h2 id="daily-changes-heading">Qué cambió</h2>
					<ul>
						{#each view.delta as linea, i (`delta-${i}`)}
							<li>
								<strong>{linea.titulo}</strong>
								{#if linea.giro}<span> — {linea.giro}</span>{/if}
							</li>
						{/each}
					</ul>
				</section>
			{/if}

			{#if view && view.vigilancia.length > 0}
				<section class="panel daily-side-panel" aria-labelledby="daily-vigilancia-heading">
					<h2 id="daily-vigilancia-heading">Vigilancia</h2>
					{#each view.vigilancia as linea, i (`vigilancia-${i}`)}
						<div class="daily-actor">
							<strong>{linea.persona}</strong>
							{#if linea.nota}<p>{linea.nota}</p>{/if}
							{#if linea.fecha}<span class="daily-actor-meta">{linea.fecha}</span>{/if}
							{#if linea.afectacion}<span class="daily-actor-meta">{linea.afectacion}</span>{/if}
						</div>
					{/each}
				</section>
			{/if}

			<section class="panel daily-side-panel daily-actors" aria-labelledby="daily-actors-heading">
				<h2 id="daily-actors-heading">Quién aparece y en qué contexto</h2>
				{#if data.persons.length > 0}
					{#each data.persons as person (person.id)}
						<div class="daily-actor">
							<!-- The name is the link: no separate «ver cobertura» CTA. -->
							<strong><a href="/persons/{person.id}">{person.name}</a></strong>
							<span class="daily-actor-meta">
								{[person.role ?? person.org, `${person.mention_count} menciones`]
									.filter(Boolean)
									.join(' · ')}
							</span>
						</div>
					{/each}
				{:else}
					<p class="daily-empty-note">No se identifican personas en los registros de esta fecha.</p>
				{/if}
			</section>
		</div>

		<aside class="daily-side" aria-label="Agenda y cobertura del día">
			<section class="panel daily-side-panel" aria-labelledby="daily-agenda-heading">
				<h2 id="daily-agenda-heading">Agenda y plazos</h2>
				{#if view && view.fechas.length > 0}
					{#each view.fechas as fecha, i (`fecha-${i}`)}
						<div class="daily-deadline">
							<span class="chip">{fecha.estado}</span>
							<strong>{fecha.titulo}</strong>
							{#if fecha.cuando}<span class="daily-actor-meta">{fecha.cuando}</span>{/if}
						</div>
					{/each}
				{:else}
					<p class="daily-empty-note">Sin fechas registradas en este resumen.</p>
				{/if}
				<a class="button daily-side-action" href="/agenda">Ver agenda completa</a>
			</section>

			<details class="panel executive-coverage">
				<summary>
					Cobertura y método
					<span>
						{coverageTotal ?? '—'}
						{coverageTotal === 1 ? 'nota registrada' : 'notas registradas'}
					</span>
				</summary>
				<div>
					<dl class="daily-coverage-list">
						<div>
							<dt>Periodo</dt>
							<dd>{formatLongDate(day)}</dd>
						</div>
						<div>
							<dt>Fuentes activas</dt>
							<dd>{data.sourcesCount ?? '—'}</dd>
						</div>
						<div>
							<dt>Eventos creados</dt>
							<dd>{liveEvents ?? '—'}</dd>
						</div>
						<div>
							<dt>Categorías con cobertura</dt>
							<dd>{activeTopics} de {TOPIC_TOTAL}</dd>
						</div>
					</dl>
					{#if categoryRowsTop.length > 0}
						<div class="coverage-extra">
							<h3>Categorías identificadas</h3>
							<p>
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
						</div>
					{/if}
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
				</div>
			</details>
		</aside>
	</div>

	{#if tarjetas.length > 0}
		<section class="section digest-evidencia" aria-labelledby="digest-evidencia-heading">
			<header class="section-heading">
				<h2 id="digest-evidencia-heading">Evidencia del día</h2>
				<span class="section-note">
					{tarjetas.length}
					{tarjetas.length === 1 ? 'historia documentada' : 'historias documentadas'}
				</span>
			</header>
			<div class="digest-tarjetas">
				{#each tarjetas as tarjeta, i (`tarjeta-${i}`)}
					<TarjetaCard {tarjeta} context={evidenceContext} />
				{/each}
			</div>
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
