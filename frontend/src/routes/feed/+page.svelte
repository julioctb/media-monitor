<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';

	import { page } from '$app/state';

	import EventGroup from '$lib/components/EventGroup.svelte';
	import { groupByEvent } from '$lib/grouping';
	import type { FeedGroup } from '$lib/grouping';
	import { CHANNEL_LABELS, type FeedChannel } from '$lib/feed-filters';
	import { BTN_PRIMARY_CLS, INPUT_CLS } from '$lib/ui';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const REFRESH_MS = 90_000;
	/** Auto-refresh while visible; pauses when the tab is hidden. */
	let refreshTimer: ReturnType<typeof setInterval> | undefined = $state();
	let lastRefresh = $state<string | null>(null);

	function startAutoRefresh() {
		stopAutoRefresh();
		refreshTimer = setInterval(() => {
			if (document.visibilityState !== 'visible') return;
			void invalidateAll().then(() => {
				lastRefresh = new Date().toLocaleTimeString('es-MX', {
					hour: '2-digit',
					minute: '2-digit'
				});
			});
		}, REFRESH_MS);
	}

	function stopAutoRefresh() {
		if (refreshTimer) clearInterval(refreshTimer);
		refreshTimer = undefined;
	}

	onMount(() => {
		startAutoRefresh();
		return stopAutoRefresh;
	});

	const filters = $derived(data.filters);

	const keywordNames = $derived(new Map(data.keywords.map((k) => [k.id, k.text])));

	/** Same event = same story: one card plus a collapsed coverage list. */
	const groups = $derived(groupByEvent(data.mentions.items));

	function keywordLabelFor(group: FeedGroup): string | null {
		const keywordId = group.mentions[0]?.keyword_id ?? null;
		return keywordId !== null ? (keywordNames.get(keywordId) ?? null) : null;
	}

	const activeKeywords = $derived(data.keywords.filter((k) => k.is_active));

	function hrefWithKeyword(keywordId: string | null): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (keywordId === null) params.delete('keyword_id');
		else params.set('keyword_id', keywordId);
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	/* Tono pills (server param `sentiment`): active pill navigates to its value,
	   clicking it again clears the param. `none` stays valid in old URLs, no pill. */
	const TONE_PILLS = [
		{ key: 'positive', label: 'Positivo' },
		{ key: 'negative', label: 'Negativo' },
		{ key: 'neutral', label: 'Neutro' }
	] as const;

	function hrefWithSentiment(value: string | null): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (value === null) params.delete('sentiment');
		else params.set('sentiment', value);
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	/* Channel tabs (server param `channel`): links, like every facet pill —
	   they preserve the rest of the query and reset pagination. */
	const CHANNEL_TABS = [
		{ value: '', label: CHANNEL_LABELS.all },
		{ value: 'news', label: CHANNEL_LABELS.news },
		{ value: 'social', label: CHANNEL_LABELS.social },
		{ value: 'field', label: CHANNEL_LABELS.field }
	] as const;

	function hrefWithChannel(value: string): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (value === '') params.delete('channel');
		else params.set('channel', value);
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	/* Tono counts from the scoped metrics (mockup tone-choice badges);
	   null when the metrics request failed — the pills stay usable. */
	const toneCounts = $derived.by(() => {
		if (!data.feedStats) return null;
		const by = data.feedStats.by_sentiment;
		return {
			all: data.feedStats.total,
			positive: by.positive ?? 0,
			negative: by.negative ?? 0,
			neutral: by.neutral ?? 0,
			none: by.none ?? 0
		};
	});

	/** Distribution segments, strongest first; a 0-count channel renders no bar. */
	const toneSegments = $derived.by(() => {
		if (!toneCounts) return [];
		return (
			[
				['positive', toneCounts.positive],
				['negative', toneCounts.negative],
				['neutral', toneCounts.neutral],
		['unclassified', toneCounts.none]
			] as const
		).filter(([, count]) => count > 0);
	});

	/* Strip v3 (mockup stats()): every figure is a measured aggregate from the
	   scoped feedStats payload — never a count over the loaded page slice. */
	const stripTotal = $derived(data.feedStats?.total ?? null);

	/** Source kinds (news/social/field) with echo among the measured results. */
	const SOURCE_KINDS = ['news', 'social', 'field'] as const;
	const stripSourceKinds = $derived.by(() => {
		if (!data.feedStats) return null;
		const echoed = new Set(
			Object.entries(data.feedStats.by_source)
				.filter(([, count]) => count > 0)
				.map(([source]) => source)
		);
		return SOURCE_KINDS.filter((kind) =>
			data.channelGroups[kind].some((source) => echoed.has(source))
		).length;
	});

	/** Distinct sources with echo among the measured results. */
	const stripSourceCount = $derived.by(() => {
		if (!data.feedStats) return null;
		return Object.values(data.feedStats.by_source).filter((count) => count > 0).length;
	});

	/* Medium facet (outlet host): links, not form posts — the panel sits
	   outside the filter form and must preserve every other facet. */
	function hrefWithMedium(value: string | null): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (value === null) params.delete('medium');
		else params.set('medium', value);
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	/** Sidebar «Medios» rows: count desc (server order), top 10 + fold. */
	const MEDIUM_TOP = 10;
	const mediumRows = $derived(
		Object.entries(data.mediumCounts ?? {}).map(([medium, count]) => ({ medium, count }))
	);
	const mediumTop = $derived(mediumRows.slice(0, MEDIUM_TOP));
	const mediumRest = $derived(mediumRows.slice(MEDIUM_TOP));

	function hrefWithOffset(offset: number): string {
		const params = new URLSearchParams(page.url.searchParams);
		params.set('offset', String(offset));
		return `${page.url.pathname}?${params.toString()}`;
	}

	/** Global navigation context, separate from the result indicators. */
	const newsTotal = $derived(
		data.channelGroups.news.reduce((sum, source) => sum + (data.sourceCounts[source] ?? 0), 0)
	);
	const socialTotal = $derived(
		data.channelGroups.social.reduce((sum, source) => sum + (data.sourceCounts[source] ?? 0), 0)
	);
	const fieldTotal = $derived(
		data.channelGroups.field.reduce((sum, source) => sum + (data.sourceCounts[source] ?? 0), 0)
	);

	const distributionRows = $derived([
		{ key: 'news', label: 'Noticias', total: newsTotal },
		{ key: 'social', label: 'Redes sociales', total: socialTotal },
		{ key: 'field', label: 'Datos de campo', total: fieldTotal }
	]);

	const pagination = $derived.by(() => {
		const { limit, offset } = filters;
		const total = data.mentions.total;
		const pages = Math.max(1, Math.ceil(total / limit));
		const current = Math.floor(offset / limit) + 1;
		return {
			from: total === 0 ? 0 : offset + 1,
			to: Math.min(offset + limit, total),
			pages,
			current,
			hasPrev: offset > 0,
			hasNext: offset + limit < total,
			prevHref: hrefWithOffset(Math.max(0, offset - limit)),
			nextHref: hrefWithOffset(offset + limit)
		};
	});

	const limitOptions = [10, 25, 50, 100];
</script>

<svelte:head>
	<title>Feed | Media Monitor</title>
</svelte:head>

<header class="feed-intro">
	<div>
		<h1 id="feed-title" class="page-title">Feed de noticias</h1>
		<p>
			Noticias y publicaciones de redes sociales en una sola vista. Filtra por fuente, tono, fecha
			o palabras del titular para revisar la cobertura.
		</p>
	</div>
	<p class="feed-refresh-status">
		Se actualiza automáticamente cada 90 segundos mientras esta pestaña esté abierta.{lastRefresh
			? ` Última actualización: ${lastRefresh}.`
			: ''}
	</p>
</header>

{#if !data.feedStats}
	<p class="footnote" role="status">{data.feedStatsError ?? 'Indicadores no disponibles.'}</p>
{/if}

<div class="feed-stats" aria-label="Números del feed">
	<div class="stat">
		<div class="stat-top"><span>Menciones en el feed</span></div>
		<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
			{stripTotal ?? '—'}</strong>
		<span class="stat-note">
			{#if stripSourceKinds !== null}{stripSourceKinds} tipos de fuente{:else}Tipos de fuente con
				registros en los resultados.{/if}
		</span>
	</div>
	<div class="stat">
		<div class="stat-top"><span>Eventos</span></div>
		<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
			{data.feedStats?.result_group_count ?? '—'}</strong>
		<span class="stat-note">Eventos y publicaciones sin evento en todos los resultados filtrados.</span>
	</div>
	<div class="stat">
		<div class="stat-top"><span>Medios con noticias</span></div>
		<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
			{data.feedStats?.news_medium_count ?? '—'}</strong>
		<span class="stat-note">Medios con registros en todos los resultados filtrados.</span>
	</div>
	<div class="stat">
		<div class="stat-top"><span>Fuentes con registros</span></div>
		<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
			{stripSourceCount ?? '—'}</strong>
		<span class="stat-note">Fuentes con publicaciones en todos los resultados filtrados.</span>
	</div>
</div>
<!-- Mockup empty-state reset («Ver todo el periodo»): the bare path drops
     every facet, the date range included. -->
<a class="feed-stats-reset text-link" href={page.url.pathname}>Ver todo el periodo</a>

<div class="feed-content-grid">
	<section class="panel feed-main" id="feed" aria-labelledby="feed-panel-title">
		<div class="feed-toolbar">
			<div class="panel-heading">
				<h2 id="feed-panel-title">Últimas menciones</h2>
			</div>

			<div class="tabs" role="group" aria-label="Filtrar por tipo de fuente">
				{#each CHANNEL_TABS as tab (tab.value)}
					<a
						class="tab"
						class:active={filters.channel === tab.value}
						role="button"
						href={hrefWithChannel(tab.value)}
						aria-pressed={filters.channel === tab.value}
					>
						{tab.label}
					</a>
				{/each}
			</div>

			<div class="tone-filter">
				<div class="tone-filter-head">
					<strong>Tono de las menciones</strong>
					<span>Clasificación automática; no evalúa veracidad.</span>
				</div>
				<div class="tone-choices" role="group" aria-label="Filtrar por tono">
					<a
						class="tone-choice"
						role="button"
						href={hrefWithSentiment(null)}
						aria-pressed={filters.sentiment === ''}
					>
						Todo{#if toneCounts}<strong>{toneCounts.all}</strong>{/if}
					</a>
					{#each TONE_PILLS as tone (tone.key)}
						<a
							class={`tone-choice tone-${tone.key}`}
							role="button"
							href={filters.sentiment === tone.key ? hrefWithSentiment(null) : hrefWithSentiment(tone.key)}
							aria-pressed={filters.sentiment === tone.key}
						>
							<span class="tone-dot" aria-hidden="true"></span>
							{tone.label}{#if toneCounts}<strong>{toneCounts[tone.key]}</strong>{/if}
						</a>
					{/each}
				</div>
				{#if toneSegments.length > 0}
					<div class="tone-bar" aria-hidden="true">
						{#each toneSegments as [segment, count] (segment)}
							<span class={`tone-segment tone-${segment}`} style={`flex:${count}`}></span>
						{/each}
					</div>
				{/if}
			</div>

			<div class="filterbar">
				<form method="get" role="search" data-testid="feed-filter-main">
					<input type="hidden" name="channel" value={filters.channel} />
					<input type="hidden" name="medium" value={filters.medium} />
					<input type="hidden" name="since" value={filters.since} />
					<input type="hidden" name="until" value={filters.until} />
					<label class="search">
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
							<path d="M20 20l-5-5 M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14" />
						</svg>
						<span class="sr-only">Buscar en el feed</span>
						<input
							type="search"
							id="f-q"
							name="q"
							value={filters.q}
							placeholder="Buscar titular o medio"
						/>
					</label>
					<button class={BTN_PRIMARY_CLS} type="submit">Buscar</button>
				</form>
			</div>

			<div class="keyword-row" role="group" aria-label="Filtrar por palabra clave monitorizada">
				<span class="keyword-label">Palabras clave:</span>
				<a
					class="keyword-chip"
					role="button"
					href={hrefWithKeyword(null)}
					aria-pressed={filters.keyword_id === ''}
				>
					Todas
				</a>
				{#each data.keywords as keyword (keyword.id)}
					<a
						class="keyword-chip"
						role="button"
						href={hrefWithKeyword(String(keyword.id))}
						aria-pressed={filters.keyword_id === String(keyword.id)}
					>
						{keyword.text}
					</a>
				{/each}
				<a href={page.url.pathname} class="text-link keyword-clear">Limpiar filtros</a>
			</div>

			<p class="feed-match-count" role="status" aria-live="polite">
				{data.mentions.total} publicaciones encontradas · ordenadas de la más reciente a la más antigua
			</p>
		</div>

		{#if data.mentions.items.length === 0}
			<div class="feed-empty" role="status">
				<h3>Sin resultados</h3>
				<p>No hay publicaciones que coincidan con estos filtros.</p>
			</div>
		{:else}
			<ol class="feed-list" aria-label="Publicaciones">
				{#each groups as group (group.key)}
					<li class="feed-group">
						<EventGroup {group} keywordLabel={keywordLabelFor(group)} />
					</li>
				{/each}
			</ol>

			<nav class="pagination" aria-label="Paginación">
				<p class="page-status">
					Página {pagination.current} de {pagination.pages} ·
					{pagination.from}–{pagination.to} de {data.mentions.total}
				</p>
				<div class="page-buttons">
					<form method="get" class="per-page">
						<!-- keep every active facet while changing the page size -->
						<input type="hidden" name="channel" value={filters.channel} />
						<input type="hidden" name="medium" value={filters.medium} />
						<input type="hidden" name="sentiment" value={filters.sentiment} />
						<input type="hidden" name="keyword_id" value={filters.keyword_id} />
						<input type="hidden" name="q" value={filters.q} />
						<input type="hidden" name="since" value={filters.since} />
						<input type="hidden" name="until" value={filters.until} />
						<label class="sr-only" for="per-page">Por página</label>
						<select
							id="per-page"
							name="limit"
							class={`per-page-select ${INPUT_CLS}`}
							onchange={(event) => event.currentTarget.form?.requestSubmit()}
						>
							{#each limitOptions as option (option)}
								<option value={String(option)} selected={filters.limit === option}>
									{option} publicaciones
								</option>
							{/each}
						</select>
					</form>
					{#if pagination.hasPrev}
						<a href={pagination.prevHref} class="button page-button">Anterior</a>
					{:else}
						<span class="button page-button" aria-disabled="true">Anterior</span>
					{/if}
					{#if pagination.hasNext}
						<a href={pagination.nextHref} class="button page-button">Siguiente</a>
					{:else}
						<span class="button page-button" aria-disabled="true">Siguiente</span>
					{/if}
				</div>
			</nav>
		{/if}
	</section>

	<div class="feed-side-column">
		<section class="panel feed-period-panel" aria-labelledby="feed-period-title">
			<div class="panel-heading">
				<h2 id="feed-period-title">Filtro de tiempo</h2>
			</div>
			<form method="get">
				<input type="hidden" name="q" value={filters.q} />
				<input type="hidden" name="sentiment" value={filters.sentiment} />
				<input type="hidden" name="keyword_id" value={filters.keyword_id} />
				<input type="hidden" name="medium" value={filters.medium} />
				<div class="feed-date-controls">
					<label>
						Desde
						<input
							type="date"
							id="date-from"
							name="since"
							value={filters.since}
							onchange={(event) => event.currentTarget.form?.requestSubmit()}
						/>
					</label>
					<label>
						Hasta
						<input
							type="date"
							id="date-to"
							name="until"
							value={filters.until}
							onchange={(event) => event.currentTarget.form?.requestSubmit()}
						/>
					</label>
				</div>
				{#if filters.dateError}
					<p class="feed-period-error" role="alert">{filters.dateError}</p>
				{/if}
				<noscript>
					<button type="submit" class="button">Aplicar</button>
				</noscript>
			</form>
		</section>

		<aside class="feed-aside" aria-label="Contexto del feed">
			<section class="panel aside-panel" aria-labelledby="origen-title">
				<div class="panel-heading">
					<h2 id="origen-title">Origen de las menciones</h2>
				</div>
				{#if newsTotal + socialTotal + fieldTotal > 0}
					<div class="distribution" aria-hidden="true">
						{#each distributionRows as row (row.key)}
							{#if row.total > 0}
								<span class={`dist-${row.key}`} style={`flex:${row.total}`}></span>
							{/if}
						{/each}
					</div>
				{/if}
				{#each distributionRows as row (row.key)}
					<div class="distribution-row">
						<span><span class={`dot dist-${row.key}`} aria-hidden="true"></span>{row.label}</span>
						<strong>{row.total}</strong>
					</div>
				{/each}
				<p class="feed-period-note">Sin aplicar los filtros del feed.</p>
			</section>

			{#if mediumRows.length > 0}
				<section class="panel aside-panel" aria-labelledby="medios-title">
					<div class="panel-heading">
						<h2 id="medios-title">Medios</h2>
					</div>
					<p class="aside-note">Medios para navegar. Sin aplicar los filtros del feed.</p>
					<div class="feed-source-list" role="group" aria-label="Filtrar por medio">
						{#if filters.medium}
							<a class="feed-source-row" role="button" href={hrefWithMedium(null)}>
								<span>Todos los medios</span>
							</a>
						{/if}
						{#each mediumTop as row (row.medium)}
							<a
								class="feed-source-row"
								role="button"
								aria-pressed={filters.medium === row.medium}
								href={hrefWithMedium(row.medium)}
							>
								<span>{row.medium}</span>
								<strong>{row.count}</strong>
							</a>
						{/each}
					</div>
					{#if mediumRest.length > 0}
						<details class="medios-more">
							<summary>Más medios ({mediumRest.length})</summary>
							<div class="feed-source-list" role="group" aria-label="Más medios">
								{#each mediumRest as row (row.medium)}
									<a
										class="feed-source-row"
										role="button"
										aria-pressed={filters.medium === row.medium}
										href={hrefWithMedium(row.medium)}
									>
										<span>{row.medium}</span>
										<strong>{row.count}</strong>
									</a>
								{/each}
							</div>
						</details>
					{/if}
				</section>
			{/if}

			<section class="panel aside-panel history-panel" aria-labelledby="historico-title">
				<div class="panel-heading">
					<h2 id="historico-title">Histórico</h2>
				</div>
				<p class="aside-note">Archivo de noticias y columnas</p>
				<div class="history-empty">
					<strong>Aún no hay registros históricos</strong>
					<p>
						Cuando se incorporen fuentes de archivo, sus resultados aparecerán en esta sección, con
						su medio y fecha de publicación original.
					</p>
				</div>
			</section>

			<section class="panel aside-panel" aria-labelledby="seguimiento-title">
				<div class="panel-heading">
					<h2 id="seguimiento-title">Seguimiento</h2>
					<a class="text-link" href="/">Volver al resumen</a>
				</div>
				<p class="aside-note">
					Los actores, categorías y temas prioritarios se resumen en la página principal.
				</p>
			</section>
		</aside>
	</div>
</div>
