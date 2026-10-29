<script lang="ts">
	import { invalidateAll, goto } from '$app/navigation';
	import { onMount } from 'svelte';

	import { page } from '$app/state';

	import MentionCard from '$lib/components/MentionCard.svelte';
	import MentionDetailDialog from '$lib/components/MentionDetailDialog.svelte';
	import EventDetailDialog from '$lib/components/EventDetailDialog.svelte';
	import type { MentionEventRef } from '$lib/components/MentionCard.svelte';
	import type { EventDetail, EventMention, Mention } from '$lib/api';
	import { groupByEvent } from '$lib/grouping';
		import { CHANNEL_LABELS, type FeedChannel } from '$lib/feed-filters';
	import { ICON_PATHS } from '$lib/icons';
	import { markSeen, prefs, seedPrefsFromServer, toggleSaved } from '$lib/prefs';
	import { notifyPersist } from '$lib/toast.svelte';
	import { INPUT_CLS } from '$lib/ui';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Single prefs seed: the store hydrates from the server-parsed cookie at
	// instance init, so saved marks and seen flags paint on first render and
	// hydration matches SSR. Intentionally once per instance (each navigation
	// re-seeds); the store itself owns later updates.
	// svelte-ignore state_referenced_locally
	seedPrefsFromServer(data.prefs);

	const savedIds = $derived($prefs.saved);
	const followedIds = $derived($prefs.follow);

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

	/** Same event = same story: one card plus a collapsed coverage list. */
	const groups = $derived(groupByEvent(data.mentions.items));

	/* Guardadas (mockup saved-filter): client-side filter over the loaded
	   page, AND-ed with the server facets — never a substitute for them. */
	let savedOnly = $state(false);

	function toggleSavedFilter() {
		savedOnly = !savedOnly;
	}

	function toggleSavedMention(id: number) {
		notifyPersist(toggleSaved(id));
	}

	/** Groups that survive the saved filter, empty groups dropped. */
	const visibleGroups = $derived.by(() => {
		if (!savedOnly) return groups;
		return groups
			.map((group) => ({
				...group,
				mentions: group.mentions.filter((mention) => savedIds.includes(mention.id))
			}))
			.filter((group) => group.mentions.length > 0);
	});

	/** Visible mention count: the counter shows what the list shows. */
	const visibleCount = $derived(visibleGroups.reduce((sum, group) => sum + group.mentions.length, 0));

	/** Record-detail dialog (mockup recordDetail): one mention at a time. */
	let detailMention: Mention | null = $state(null);
	let detailEvent: MentionEventRef | null = $state(null);

	function openDetail(mention: Mention, event: MentionEventRef | null) {
		expedient = null;
		detailMention = mention;
		detailEvent = event;
	}

	/** Event-detail dialog (mockup eventDetail, "Expediente #id"). */
	let expedient: EventDetail | null = $state(null);

	function openEvent(ref: MentionEventRef) {
		const full = data.eventsById[ref.id];
		if (full) {
			expedient = full;
			// Mockup eventDetail: opening the file marks a followed event seen.
			if (followedIds.includes(ref.id) && full.last_seen_at) markSeen(ref.id, full.last_seen_at);
		}
		// without server payload (failed fetch) the chip stays a link to /events
	}

	/** "Leer registro original" from the expediente: chain into the record
	   dialog with the full mention when this page carries it. */
	function openEventRecord(stub: EventMention) {
		const current = expedient;
		const full = data.mentions.items.find((m) => m.id === stub.id);
		expedient = null;
		detailMention = full ?? (stub as unknown as Mention);
		detailEvent = current ? { id: current.id, title: current.title } : null;
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
		{ value: '', label: CHANNEL_LABELS.all, icon: 'layers' },
		{ value: 'news', label: CHANNEL_LABELS.news, icon: 'feed' },
		{ value: 'social', label: CHANNEL_LABELS.social, icon: 'social' },
		{ value: 'field', label: CHANNEL_LABELS.field, icon: 'field' }
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
		{ key: 'field', label: 'Campo', total: fieldTotal }
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

	/* Which v3 empty state applies: filtered-out vs empty period. The saved
	   filter joins the facet set (mockup feedBase ANDs savedOnly). */
	const filtersActive = $derived(
		Boolean(
			filters.channel ||
				filters.sentiment ||
				filters.q ||
				filters.medium ||
				filters.since ||
				filters.until ||
				savedOnly
		)
	);

	/* Period presets (mockup #feed-period-preset): every option resolves to
	   the same server params (since/until) the custom range uses. */
	function isoDay(offsetFromToday: number): string {
		const day = new Date();
		day.setDate(day.getDate() + offsetFromToday);
		return day.toISOString().slice(0, 10);
	}
	const PERIOD_PRESETS = [
		{ value: 'today', label: 'Hoy', since: () => isoDay(0), until: () => isoDay(0) },
		{ value: 'yesterday', label: 'Ayer', since: () => isoDay(-1), until: () => isoDay(-1) },
		{
			value: 'yesterdayToday',
			label: 'Ayer y hoy',
			since: () => isoDay(-1),
			until: () => isoDay(0)
		},
		{ value: 'last10', label: 'Últimos 10 días', since: () => isoDay(-9), until: () => isoDay(0) },
		{ value: 'lastMonth', label: 'Último mes', since: () => isoDay(-29), until: () => isoDay(0) },
		{ value: 'custom', label: 'Personalizado' },
		{ value: 'all', label: 'Todo el periodo' }
	] as const;
	type PeriodPreset = (typeof PERIOD_PRESETS)[number]['value'];

	function hrefWithPeriod(preset: PeriodPreset): string {
		const params = new URLSearchParams(page.url.searchParams);
		if (preset === 'all') {
			params.delete('since');
			params.delete('until');
		} else if (preset !== 'custom') {
			const def = PERIOD_PRESETS.find((p) => p.value === preset);
			if (def && 'since' in def) {
				params.set('since', def.since());
				params.set('until', def.until());
			}
		}
		params.delete('offset'); // a new filter facet resets pagination
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	/* Active preset derived from the loaded range: a known preset when the
	   dates match it exactly, 'custom' when dates are set, 'all' otherwise. */
	const activePreset = $derived.by(() => {
		const { since, until } = filters;
		if (!since && !until) return 'all' as const;
		for (const def of PERIOD_PRESETS) {
			if ('since' in def && def.since() === since && def.until() === until) {
				return def.value;
			}
		}
		return 'custom' as const;
	});

	function applyPeriodPreset(event: Event) {
		const value = (event.currentTarget as HTMLSelectElement).value as PeriodPreset;
		if (value !== 'custom') void goto(hrefWithPeriod(value), { noScroll: true });
	}

	/* Channel source rows (mockup sourceBreakdown): label + global count,
	   only sources with echo — a channel without rows renders no panel. */
	function channelSourceRows(channel: Exclude<FeedChannel, ''>) {
		return data.channelGroups[channel]
			.map((source) => ({ source, count: data.sourceCounts[source] ?? 0 }))
			.filter((row) => row.count > 0);
	}
	const socialSourceRows = $derived(channelSourceRows('social'));
	const fieldSourceRows = $derived(channelSourceRows('field'));
</script>

<svelte:head>
	<title>Feed | Media Monitor</title>
</svelte:head>

<header class="feed-intro">
	<div>
		<h1 id="feed-title" class="page-title">Feed de noticias</h1>
		<p>Todas las fuentes. Un solo lugar para entender lo que pasa.</p>
	</div>
	<p
		class="feed-refresh-status"
		title="Se actualiza automáticamente cada 90 segundos mientras esta pestaña esté abierta."
	>
		<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
			<path d={ICON_PATHS.clock} />
		</svg>
		<span>Última actualización {lastRefresh ?? '—'}</span>
	</p>
</header>

{#if !data.feedStats}
	<p class="footnote" role="status">{data.feedStatsError ?? 'Indicadores no disponibles.'}</p>
{/if}

<div class="feed-stats" aria-label="Números del feed">
	<div class="stat">
		<div class="stat-top">
			<span>Menciones en el feed</span>
			<span class="stat-icon news" aria-hidden="true">
				<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.feed} /></svg>
			</span>
		</div>
		<div class="od-stat">
			<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
				{stripTotal ?? '—'}
			</strong>
			<span class="stat-note">
				{#if stripSourceKinds !== null}{stripSourceKinds} tipos de fuente{:else}Tipos de fuente con
					registros en los resultados.{/if}
			</span>
		</div>
	</div>
	<div class="stat">
		<div class="stat-top">
			<span>Eventos</span>
			<span class="stat-icon neutral" aria-hidden="true">
				<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.events} /></svg>
			</span>
		</div>
		<div class="od-stat">
			<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
				{data.feedStats?.result_group_count ?? '—'}
			</strong>
			<span class="stat-note">Eventos y publicaciones sin evento en todos los resultados filtrados.</span>
		</div>
	</div>
	<div class="stat">
		<div class="stat-top">
			<span>Medios con noticias</span>
			<span class="stat-icon field" aria-hidden="true">
				<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.layers} /></svg>
			</span>
		</div>
		<div class="od-stat">
			<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
				{data.feedStats?.news_medium_count ?? '—'}
			</strong>
			<span class="stat-note">Medios con registros en todos los resultados filtrados.</span>
		</div>
	</div>
	<div class="stat">
		<div class="stat-top">
			<span>Fuentes con registros</span>
			<span class="stat-icon social" aria-hidden="true">
				<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.social} /></svg>
			</span>
		</div>
		<div class="od-stat">
			<strong class="stat-value" title={data.feedStats ? undefined : 'No disponible'}>
				{stripSourceCount ?? '—'}
			</strong>
			<span class="stat-note">Fuentes con publicaciones en todos los resultados filtrados.</span>
		</div>
	</div>
</div>
<div class="feed-content-grid">
	<section class="panel feed-main" id="feed" aria-labelledby="feed-panel-title">
		<div class="feed-toolbar">
			<div class="panel-heading">
				<h2 id="feed-panel-title">Últimas menciones</h2>
				<!-- Mockup saved-filter: bookmark toggle, pressed state, session-scoped. -->
				<button
					type="button"
					class="text-link"
					id="saved-filter"
					aria-pressed={savedOnly}
					onclick={toggleSavedFilter}
				>
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
						<path d={ICON_PATHS.bookmark} />
					</svg>
					{savedOnly ? 'Ver todas' : 'Guardadas'}
				</button>
			</div>

			<div class="tabs" role="group" aria-label="Filtrar por tipo de fuente">
				{#each CHANNEL_TABS as tab (tab.value)}
					<a
						class="tab"
						class:active={filters.channel === tab.value}
						role="button"
						href={hrefWithChannel(tab.value)}
						aria-pressed={filters.channel === tab.value}
						data-sveltekit-noscroll
					>
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
							<path d={ICON_PATHS[tab.icon]} />
						</svg>
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
						data-sveltekit-noscroll
					>
						Todos{#if toneCounts}<strong>{toneCounts.all}</strong>{/if}
					</a>
					{#each TONE_PILLS as tone (tone.key)}
						<a
							class={`tone-choice tone-${tone.key}`}
							role="button"
							href={filters.sentiment === tone.key ? hrefWithSentiment(null) : hrefWithSentiment(tone.key)}
							aria-pressed={filters.sentiment === tone.key}
							data-sveltekit-noscroll
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
							<path d={ICON_PATHS.search} />
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
					<button class="sr-only" type="submit">Buscar</button>
				</form>
			</div>

			<p class="feed-match-count" role="status" aria-live="polite">
				{#if savedOnly}
					{visibleCount} publicaciones encontradas · ordenadas de la más reciente a la más antigua
				{:else}
					{data.mentions.total} publicaciones encontradas · ordenadas de la más reciente a la más
					antigua
				{/if}
			</p>
		</div>

		{#if visibleGroups.length === 0}
			<div class="feed-empty" role="status">
				{#if filtersActive}
					<h3>No hay menciones con estos filtros</h3>
					<p>Prueba otra búsqueda o revisa las fuentes activas.</p>
					<a class="button" href={page.url.pathname}>Limpiar filtros</a>
				{:else}
					<h3>No hay menciones en este periodo</h3>
					<p>Prueba «Ayer y hoy» u otro periodo para consultar los registros disponibles.</p>
					<a class="button" href={page.url.pathname}>Ver todo el periodo</a>
				{/if}
			</div>
		{:else}
			<ol class="feed-list" aria-label="Publicaciones">
				{#each visibleGroups as group (group.key)}
					<li class="feed-group">
						{#each group.mentions as mention (mention.id)}
							<MentionCard
								{mention}
								event={group.event}
								coverageCount={group.mentions.length}
								saved={savedIds.includes(mention.id)}
								onSave={() => toggleSavedMention(mention.id)}
								onDetail={(m) => openDetail(m, group.event)}
								onEvent={group.event && data.eventsById[group.event.id] ? openEvent : undefined}
							/>
						{/each}
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
		<section class="panel aside-panel feed-period-panel" aria-labelledby="feed-period-title">
			<div class="panel-heading">
				<h2 id="feed-period-title">Filtro de tiempo</h2>
			</div>
			<label class="feed-period-preset">
				Periodo
				<select id="feed-period-preset" value={activePreset} onchange={applyPeriodPreset}>
					{#each PERIOD_PRESETS as preset (preset.value)}
						<option value={preset.value}>{preset.label}</option>
					{/each}
				</select>
			</label>
			<form method="get">
				<input type="hidden" name="q" value={filters.q} />
				<input type="hidden" name="sentiment" value={filters.sentiment} />
				<input type="hidden" name="medium" value={filters.medium} />
				{#if activePreset === 'custom'}
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
						<p class="feed-period-note">Incluye ambas fechas.</p>
					</div>
				{/if}
				{#if filters.dateError}
					<p class="feed-period-error" role="alert">{filters.dateError}</p>
				{/if}
				<noscript>
					<button type="submit" class="button">Aplicar</button>
				</noscript>
			</form>
		</section>

		<aside class="feed-aside" aria-label="Contexto del feed">
			<!-- Mockup asideContent: «Eventos en foco» heads the rail. -->
			<section class="panel aside-panel" aria-labelledby="focus-title">
				<div class="panel-heading">
					<h2 id="focus-title">Eventos en foco</h2>
					<a class="text-link" href="/events">
						Ver todos
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
							<path d={ICON_PATHS.chevron} />
						</svg>
					</a>
				</div>
				{#if data.prefs.follow.length === 0}
					<p class="focus-events-empty">Aún no sigues eventos. Puedes marcarlos en la página Eventos.</p>
				{:else if data.focusEvents.length === 0}
					<p class="focus-events-empty">Sin menciones de eventos en foco en este periodo.</p>
				{:else}
					{#each data.focusEvents as row (row.id)}
						<button
							type="button"
							class="event-mini"
							onclick={() => openEvent({ id: row.id, title: row.title })}
						>
							<span class="mini-id">
								<span>EVENTO #{row.id}</span>
								<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
									<path d={ICON_PATHS.arrow} />
								</svg>
							</span>
							<span class="mini-title">{row.title}</span>
							{#if followedIds.includes(row.id) && data.eventsById[row.id]
								&& $prefs.seen[String(row.id)] !== data.eventsById[row.id]?.last_seen_at}
								<span class="event-unread">
									<span class="event-unread-dot" aria-hidden="true"></span>
									Actualizado · sin ver
								</span>
							{/if}
							<span class="mini-count">
								<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
									<path d={ICON_PATHS.layers} />
								</svg>
								{row.mentions} menciones
								<span>{row.sourceKinds} tipos de fuente</span>
							</span>
						</button>
					{/each}
				{/if}
			</section>

			<section class="panel aside-panel" aria-labelledby="origen-title">
				<div class="panel-heading">
					<h2 id="origen-title">Origen de las menciones</h2>
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
						<path d={ICON_PATHS.layers} />
					</svg>
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
						<h2 id="medios-title">Medios detectados</h2>
					</div>
					<div class="feed-source-list" role="group" aria-label="Filtrar por medio">
						{#if filters.medium}
							<a class="feed-source-row" role="button" href={hrefWithMedium(null)} data-sveltekit-noscroll>
								<span>Todos los medios</span>
							</a>
						{/if}
						{#each mediumTop as row (row.medium)}
							<a
								class="feed-source-row"
								role="button"
								aria-pressed={filters.medium === row.medium}
								href={hrefWithMedium(row.medium)}
								data-sveltekit-noscroll
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
										data-sveltekit-noscroll
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

			{#if socialSourceRows.length > 0}
				<section class="panel aside-panel" aria-labelledby="redes-title">
					<div class="panel-heading">
						<h2 id="redes-title">Redes sociales</h2>
					</div>
					<div class="feed-source-list" role="group" aria-label="Fuentes de redes sociales">
						{#each socialSourceRows as row (row.source)}
							<span class="feed-source-row">
								<span>{row.source}</span>
								<strong>{row.count}</strong>
							</span>
						{/each}
					</div>
				</section>
			{/if}

			{#if fieldSourceRows.length > 0}
				<section class="panel aside-panel" aria-labelledby="campo-title">
					<div class="panel-heading">
						<h2 id="campo-title">Campo</h2>
					</div>
					<div class="feed-source-list" role="group" aria-label="Fuentes de campo">
						{#each fieldSourceRows as row (row.source)}
							<span class="feed-source-row">
								<span>{row.source}</span>
								<strong>{row.count}</strong>
							</span>
						{/each}
					</div>
				</section>
			{/if}
		</aside>
	</div>
</div>

{#if expedient}
	<EventDetailDialog event={expedient} onRecord={openEventRecord} onclose={() => (expedient = null)} />
{/if}
<MentionDetailDialog
	mention={detailMention}
	event={detailEvent}
	onclose={() => (detailMention = null)}
/>
