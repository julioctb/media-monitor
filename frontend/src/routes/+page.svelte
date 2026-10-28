<script lang="ts">
	import { invalidateAll, goto } from '$app/navigation';
	import { onMount } from 'svelte';

	import {
		calendarParts,
		formatDayLabel,
		formatDisplayDateTime,
		formatDisplayTime,
		formatLongDate,
		nextCutLabel,
		sourceLabel
	} from '$lib/format';
	import DigestEvidence from '$lib/components/DigestEvidence.svelte';
	import { createEvidenceContext } from '$lib/digest-evidence';
	import { digestV3View, type BriefEntryView } from '$lib/digest-v3';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const summary = $derived(data.summary);
	const evidenceContext = $derived(createEvidenceContext(summary?.content));
	const day = $derived(data.day);

	// Auto-refresh while visible (same contract as the feed): picks up new
	// digest cuts and live counts without a manual reload.
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

	/** Mockup caps priorities at three (its «otros asuntos» branch is
	 * unreachable with demo data — the visible contract is three, period). */
	const MAX_PRIORITIES = 3;
	const topPicks = $derived(picks.slice(0, MAX_PRIORITIES));

	/** Delta lines keyed by their resolved story title — feeds each card's
	 * «Cambio respecto al corte anterior» row (mockup inline facts row). */
	const deltaByTitle = $derived(
		new Map((view?.delta ?? []).map((linea) => [linea.titulo, linea.giro ?? linea.titulo]))
	);

	function changeForPick(pick: AttentionPick): string | null {
		return deltaByTitle.get(pick.titulo) ?? null;
	}

	/** Mockup's parallel «Decisiones y acciones sugeridas»: picks with an action. */
	const acciones = $derived(picks.filter((pick) => pick.accionSugerida || pick.condicion));

	/** Evidence dialog (mockup dailyEvidence): one open asunto at a time. */
	let evidencePick: AttentionPick | null = $state(null);
	let evidenceDialog: HTMLDialogElement | null = null;

	function openEvidence(pick: AttentionPick) {
		evidencePick = pick;
		// jsdom no implementa showModal; los navegadores reales sí (patrón campo).
		if (typeof evidenceDialog?.showModal === 'function') evidenceDialog.showModal();
	}

	/** Documented fact for a story, from the tarjeta pool (no invention). */
	function hechoFor(titulo: string): string | null {
		return view?.tarjetas.find((tarjeta) => tarjeta.titulo === titulo)?.hecho ?? null;
	}

	const calendar = $derived(calendarParts(day));

	const activeTopics = $derived(data.liveCoverage ? Object.keys(data.liveCoverage.byTopic).length : 0);
	const TOPIC_TOTAL = 9;

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

	{#snippet datePicker()}
		<div class="briefing-date-picker">
			<label for="day-jump">Cambiar fecha</label>
			<select
				id="day-jump"
				value={day}
				disabled={data.days.length === 0}
				onchange={(event) => goto(`?date=${event.currentTarget.value}`)}
			>
				{#if data.days.length > 0}
					{#each data.days as entry (entry.summary_date)}
						<option value={entry.summary_date}>
							{formatLongDate(entry.summary_date)}
						</option>
					{/each}
				{:else}
					<option value="">Sin fechas con registros</option>
				{/if}
			</select>
			{#if olderHref}
				<a class="text-link" href={olderHref}>ver mes anterior</a>
			{/if}
		</div>
	{/snippet}

	<!-- Mockup shell intro: page title row with the date picker on the right
	     (render() moves the picker into .intro on the daily view). -->
	<header class="intro">
		<h2 class="intro-title">Resumen diario</h2>
		{@render datePicker()}
	</header>

	{#snippet dateControl()}
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
			</div>
		</div>
	{/snippet}

	{#if summary}
		<!-- Mockup daily-summary-row: editorial synthesis + date/cut control. -->
		<div class="daily-summary-row">
			<section class="daily-synthesis" aria-labelledby="daily-synthesis-title">
				<div class="daily-synthesis-heading">
					<h2 id="daily-synthesis-title">Síntesis del día</h2>
					<span>{eyebrow}</span>
				</div>
				<div class="daily-synthesis-copy">
					{#if lead}
						<p class="daily-synthesis-lead">{lead}</p>
						<DigestEvidence context={evidenceContext} request={headlineRequest} />
					{/if}
				</div>
				{#if lastRefresh}
					<p class="daily-synthesis-context">Refrescado a las {lastRefresh}.</p>
				{/if}
			</section>
			{@render dateControl()}
		</div>

		{#if topPicks.length > 0}
			<!-- Mockup executive block: up to three priorities, then «otros asuntos». -->
			<div class="executive-heading">
				<h2>Qué requiere atención</h2>
				<span class="executive-note">
					Hasta tres asuntos · prioridad editorial, no volumen de publicaciones
				</span>
			</div>
			<div class="executive-priorities">
				{#each topPicks as pick, i (`${pick.category}-${i}`)}
					<article class="panel executive-priority">
						<div class="executive-card-top">
							<span class="daily-number">{String(i + 1).padStart(2, '0')}</span>
							<span class="source-badge">{pick.category}</span>
						</div>
						<h3>{pick.titulo}</h3>
						{#if pick.razon}<p class="executive-reason">{pick.razon}</p>{/if}
						<dl class="executive-facts">
							{#if pick.afectacion}
								<div>
									<dt>Por qué importa <span>· lectura política</span></dt>
									<dd>{pick.afectacion}</dd>
								</div>
							{/if}
							<div>
								<dt>Cambio respecto al corte anterior</dt>
								<dd>
									{changeForPick(pick) ??
										'No establecido: falta una comparación de hechos validada.'}
								</dd>
							</div>
						</dl>
						<div class="executive-evidence">
							<button type="button" class="text-link" onclick={() => openEvidence(pick)}>
								Ver fuentes y detalle
							</button>
						</div>
					</article>
				{/each}
			</div>
		{/if}
	{:else}
		{@render dateControl()}
		<section class="panel empty">
			<h2>Sin información para elaborar el resumen</h2>
			<p>No hay registros en esta fecha. La ausencia de datos no implica ausencia de incidentes.</p>
		</section>
	{/if}

	{#if summary}
		<!-- Mockup daily-layout: actions/people main column + agenda/coverage side. -->
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
									<button type="button" class="text-link" onclick={() => openEvidence(pick)}>
										Consultar evidencia
									</button>
								</article>
							{/each}
						{:else}
							<p class="daily-empty-note">Sin acciones sugeridas en el corte de este día.</p>
						{/if}
					</section>
				{/if}

				<section class="panel daily-side-panel daily-actors" aria-labelledby="daily-actors-heading">
					<h2 id="daily-actors-heading">Quién aparece y en qué contexto</h2>
					<p class="daily-actors-note">Una mención no atribuye responsabilidad.</p>
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
						<p class="daily-empty-note">No se identifican personajes en los registros de esta fecha.</p>
					{/if}
				</section>
			</div>

			<aside class="daily-side" aria-label="Agenda y cobertura del día">
				<section class="panel daily-side-panel" aria-labelledby="daily-agenda-heading">
					<h2 id="daily-agenda-heading">Agenda y plazos</h2>
					<p class="daily-actors-note">
						Fechas extraídas de publicaciones; requieren confirmación antes de tratarse como compromisos.
					</p>
					{#if view && view.fechas.length > 0}
						{#each view.fechas as fecha, i (`fecha-${i}`)}
							{@const parts = calendarParts(fecha.fechaIso ?? '')}
							<div class="daily-upcoming">
								{#if parts}
									<div class="date-box od-cell" aria-hidden="true">
										<span>{parts.monthYear.split(' ')[0].slice(0, 3).toUpperCase()}</span>
										<strong>{parts.day}</strong>
									</div>
								{/if}
								<div>
									<strong>{fecha.titulo}</strong>
									{#if fecha.cuando}
										<span class="daily-actor-meta">{fecha.cuando} · Fecha detectada en publicación</span>
									{/if}
									<span class="daily-actor-meta">Estado: {fecha.estado}; compromiso no confirmado</span>
								</div>
							</div>
						{/each}
					{:else}
						<p class="daily-empty-note">Sin fechas futuras detectadas en los registros de este corte.</p>
					{/if}
					<a class="button daily-side-action" href="/agenda">Ver agenda completa</a>
				</section>

				<details class="panel executive-coverage">
					<summary>
						Cobertura y método
						<span>
							{coverageTotal ?? '—'}
							{coverageTotal === 1 ? 'publicación analizada' : 'publicaciones analizadas'}
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
						<p class="daily-veracity">Veracidad no evaluada</p>
					</div>
				</details>
			</aside>
		</div>
	{/if}

	<!-- Mockup dailyEvidence dialog: hecho reportado, lectura política y
	     materiales del corte para el asunto abierto. -->
	<dialog
		class="detail-dialog"
		bind:this={evidenceDialog}
		aria-labelledby="daily-evidence-title"
		onclose={() => (evidencePick = null)}
	>
		<div class="dialog-head">
			<strong id="daily-evidence-title">Evidencia del asunto</strong>
			<button type="button" class="icon-button" onclick={() => evidenceDialog?.close()} aria-label="Cerrar">
				Cerrar
			</button>
		</div>
		<div class="dialog-body">
			{#if evidencePick}
				<p class="daily-dialog-eyebrow">Resumen del {formatDayLabel(day)}</p>
				<h2 class="daily-dialog-title">{evidencePick.titulo}</h2>
				{#if hechoFor(evidencePick.titulo)}
					<section>
						<h3>Hecho reportado</h3>
						<p>{hechoFor(evidencePick.titulo)}</p>
					</section>
				{/if}
				{#if evidencePick.razon}
					<section class="daily-dialog-interpretation">
						<h3>Lectura política · interpretación</h3>
						<p>{evidencePick.razon}</p>
						<p class="daily-dialog-warning">
							<strong>No respaldada como hecho.</strong>
							Esta lectura editorial no acredita por sí misma el impacto descrito.
						</p>
					</section>
				{/if}
				{#await evidenceContext}
					<p class="daily-empty-note">Cargando evidencia…</p>
				{:then catalogue}
					{@const refs = Array.isArray(evidencePick.sourceRefs)
						? evidencePick.sourceRefs.filter((ref): ref is number => Number.isInteger(ref))
						: []}
					{@const materials = refs
						.map((idx) => catalogue?.sources[idx])
						.filter((m): m is NonNullable<typeof m> => Boolean(m))}
					<h3>Materiales del corte actual · {materials.length}</h3>
					{#if materials.length === 0}
						<p class="daily-empty-note">No hay fuentes vinculadas a esta entrada en el corte.</p>
					{:else}
						{#each materials as material (material.index)}
							<article class="daily-dialog-record">
								<span class="source-badge">{sourceLabel(material.source)}</span>
								{#if material.title}<h4>{material.title}</h4>{/if}
								{#if material.excerpt ?? material.summary}
									<p>{material.excerpt ?? material.summary}</p>
								{/if}
								<p class="daily-dialog-meta">
									{material.outlet}
									{material.published_at ? ` · ${formatDisplayDateTime(material.published_at)}` : ''}
								</p>
								{#if material.url}
									<a class="text-link" href={material.url} target="_blank" rel="noreferrer">
										Leer registro original
									</a>
								{/if}
							</article>
						{/each}
					{/if}
				{:catch}
					<p class="daily-empty-note">Sin catálogo de evidencia en este corte.</p>
				{/await}
				<p class="daily-dialog-footnote">Veracidad no evaluada</p>
			{/if}
		</div>
	</dialog>
</div>
