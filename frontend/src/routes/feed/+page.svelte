<script lang="ts">
	import { invalidateAll } from '$app/navigation';
	import { onMount } from 'svelte';

	import { page } from '$app/state';

	import EventGroup from '$lib/components/EventGroup.svelte';
	import { groupByEvent } from '$lib/grouping';
	import type { FeedGroup } from '$lib/grouping';
	import { CHANNEL_LABELS, type FeedChannel } from '$lib/feed-filters';
	import { INPUT_CLS } from '$lib/ui';
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
		{ key: 'neutral', label: 'Neutro' },
		{ key: 'negative', label: 'Negativo' }
	] as const;

	function hrefWithSentiment(value: string | null): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (value === null) params.delete('sentiment');
		else params.set('sentiment', value);
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

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

<section class="intro" aria-labelledby="feed-title">
	<div class="intro-content">
		<div class="eyebrow">Monitor de medios · BUAP</div>
		<h1 id="feed-title" class="page-title">Feed de noticias</h1>
		<p class="intro-copy">
			Noticias y publicaciones de redes sociales en una sola vista. Filtra por fuente, tono,
			fecha o palabras del titular para revisar la cobertura.
		</p>
		<p class="footnote">
			Se actualiza automáticamente cada 90 segundos mientras esta pestaña esté
			abierta.{lastRefresh ? ` Última actualización: ${lastRefresh}.` : ''}
		</p>
	</div>
	<div class="intro-stats" aria-label="Números del feed">
		<article class="intro-stat">
			<p class="intro-stat-label">Medios con noticias</p>
			<p class="intro-stat-value" title={data.feedStats ? undefined : 'No disponible'}>{data.feedStats?.news_medium_count ?? '—'}</p>
			<p class="intro-stat-note">Medios con registros en todos los resultados filtrados.</p>
		</article>
		<article class="intro-stat">
			<p class="intro-stat-label">Eventos</p>
			<p class="intro-stat-value" title={data.feedStats ? undefined : 'No disponible'}>{data.feedStats?.result_group_count ?? '—'}</p>
			<p class="intro-stat-note">Eventos y publicaciones sin evento en todos los resultados filtrados.</p>
		</article>
	</div>
</section>

{#if !data.feedStats}
	<p class="footnote" role="status">{data.feedStatsError ?? 'Indicadores no disponibles.'}</p>
{/if}

<div class="layout">
	<div class="feed-main">
		<section class="panel feed-filter-panel" aria-labelledby="filter-panel-title">
			<h2 id="filter-panel-title">Filtrar publicaciones</h2>
			<form method="get" role="search" data-testid="feed-filter-main">
				<input type="hidden" name="channel" value={filters.channel} />
				<input type="hidden" name="medium" value={filters.medium} />
				<input type="hidden" name="since" value={filters.since} />
				<input type="hidden" name="until" value={filters.until} />
				<div class="filter-bar">
					<div>
						<label class="filter-label" for="f-q">Buscar en el feed</label>
						<input
							type="search"
							id="f-q"
							name="q"
							value={filters.q}
							placeholder="Buscar titular o medio"
							class={INPUT_CLS}
						/>
					</div>
					<div>
						<span class="filter-label" id="f-sentiment-label">Tono</span>
						<div class="feed-filters" role="group" aria-labelledby="f-sentiment-label">
							{#each TONE_PILLS as tone (tone.key)}
								<a
									class="feed-filter tone-{tone.key}"
									role="button"
									href={filters.sentiment === tone.key
										? hrefWithSentiment(null)
										: hrefWithSentiment(tone.key)}
									aria-pressed={filters.sentiment === tone.key}
								>
									{tone.label}
								</a>
							{/each}
						</div>
					</div>
					<button class="search-button" type="submit">Buscar</button>
				</div>
				<div class="keyword-filter" role="group" aria-label="Filtrar por palabra clave monitorizada">
					<span class="keyword-label">Palabras clave:</span>
					<button type="submit" name="keyword_id" value="" class="chip" aria-pressed={filters.keyword_id === ''}>
						Todas
					</button>
					{#each data.keywords as keyword (keyword.id)}
						<button
							type="submit"
							name="keyword_id"
							value={String(keyword.id)}
							class="chip"
							aria-pressed={filters.keyword_id === String(keyword.id)}
						>
							{keyword.text}
						</button>
					{/each}
					<a href={page.url.pathname} class="clear-link keyword-clear">Limpiar filtros</a>
				</div>
			</form>
		</section>

		<section class="panel feed-panel" id="feed" aria-labelledby="cobertura-title">
			<div class="section-heading">
				<h2 id="cobertura-title" class="panel-title">Cobertura reciente</h2>
				<span class="section-note">Ordenada de más reciente a más antigua</span>
			</div>
			<p class="result-line">
				<span>{data.mentions.total} publicaciones encontradas</span>
			</p>

			{#if data.mentions.items.length === 0}
				<div class="error-state" role="status">
					<strong>Sin resultados</strong>
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
								<a href={pagination.prevHref} class="page-button">Anterior</a>
							{:else}
								<span class="page-button" aria-disabled="true">Anterior</span>
							{/if}
							{#if pagination.hasNext}
								<a href={pagination.nextHref} class="page-button">Siguiente</a>
							{:else}
								<span class="page-button" aria-disabled="true">Siguiente</span>
							{/if}
					</div>
				</nav>
			{/if}
		</section>
	</div>

	<aside class="sidebar" aria-label="Filtros, histórico y estado">
		<section class="sidebar-section" aria-labelledby="filtro-title">
			<h2 id="filtro-title">Filtrar feed</h2>
			<form method="get" class="filter-stack">
				<input type="hidden" name="q" value={filters.q} />
				<input type="hidden" name="sentiment" value={filters.sentiment} />
				<input type="hidden" name="keyword_id" value={filters.keyword_id} />
				<input type="hidden" name="medium" value={filters.medium} />

				<fieldset class="filter-group" aria-label="Filtrar por tipo de contenido">
					<button
						type="submit"
						name="channel"
						value=""
						class="filter"
						aria-pressed={filters.channel === ''}
					>
						{CHANNEL_LABELS.all}
					</button>
					<button
						type="submit"
						name="channel"
						value="news"
						class="filter"
						aria-pressed={filters.channel === 'news'}
					>
						{CHANNEL_LABELS.news}
					</button>
					<button
						type="submit"
						name="channel"
						value="social"
						class="filter"
						aria-pressed={filters.channel === 'social'}
					>
						{CHANNEL_LABELS.social}
					</button>
					<button
						type="submit"
						name="channel"
						value="field"
						class="filter"
						aria-pressed={filters.channel === 'field'}
					>
						{CHANNEL_LABELS.field}
					</button>
				</fieldset>

				<div class="date-row">
					<div>
						<label class="filter-label" for="date-from">Desde</label>
						<input
							type="date"
							id="date-from"
							name="since"
							value={filters.since}
							class={INPUT_CLS}
							onchange={(event) => event.currentTarget.form?.requestSubmit()}
						/>
					</div>
					<div>
						<label class="filter-label" for="date-to">Hasta</label>
						<input
							type="date"
							id="date-to"
							name="until"
							value={filters.until}
							class={INPUT_CLS}
							onchange={(event) => event.currentTarget.form?.requestSubmit()}
						/>
					</div>
				</div>
				{#if filters.dateError}
					<p class="date-error">{filters.dateError}</p>
				{/if}

				<noscript>
					<button type="submit" class="filter">Aplicar</button>
				</noscript>
			</form>
		</section>

		{#if mediumRows.length > 0}
			<section class="sidebar-section" aria-labelledby="medios-title">
				<h2 id="medios-title">Medios</h2>
				<p class="side-note">Medios para navegar. Sin aplicar los filtros del feed.</p>
				<div class="filter-group medios-group" role="group" aria-label="Filtrar por medio">
					{#if filters.medium}
						<a class="filter" href={hrefWithMedium(null)}>Todos los medios</a>
					{/if}
					{#each mediumTop as row (row.medium)}
						<a
							class="filter"
							role="button"
							aria-pressed={filters.medium === row.medium}
							href={hrefWithMedium(row.medium)}
						>
							{row.medium} · {row.count}
						</a>
					{/each}
				</div>
				{#if mediumRest.length > 0}
					<details class="medios-more">
						<summary>Más medios ({mediumRest.length})</summary>
						<div class="filter-group medios-group" role="group" aria-label="Más medios">
							{#each mediumRest as row (row.medium)}
								<a
									class="filter"
									role="button"
									aria-pressed={filters.medium === row.medium}
									href={hrefWithMedium(row.medium)}
								>
									{row.medium} · {row.count}
								</a>
							{/each}
						</div>
					</details>
				{/if}
			</section>
		{/if}

		<section class="sidebar-section history-panel" aria-labelledby="historico-title">
			<h2 id="historico-title">Histórico</h2>
			<p class="side-note">Archivo de noticias y columnas</p>
			<div class="history-empty">
				<strong>Aún no hay registros históricos</strong>
				<p>
					Cuando se incorporen fuentes de archivo, sus resultados aparecerán en esta sección,
					con su medio y fecha de publicación original.
				</p>
			</div>
		</section>

		<section class="sidebar-section" aria-labelledby="estado-title">
			<h2 id="estado-title">Estado de las fuentes</h2>
			<p class="side-note">Sin aplicar los filtros del feed.</p>
			<p><strong>Noticias:</strong> {newsTotal} registros.</p>
			<p><strong>Redes sociales:</strong> {socialTotal} registros.</p>
			<p><strong>Datos de campo:</strong> sin registros cargados.</p>
		</section>

		<section class="sidebar-section" aria-labelledby="seguimiento-title">
			<h2 id="seguimiento-title">Seguimiento</h2>
			<p class="side-note">
				Los actores, categorías y temas prioritarios se resumen en la página principal.
			</p>
			<a class="back" href="/">Volver al resumen →</a>
		</section>
	</aside>
</div>
