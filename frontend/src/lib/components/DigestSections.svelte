<script lang="ts">
	import NewsEntry from '$lib/components/NewsEntry.svelte';
	import { sourceLabel, sentimentLabel, topicLabel } from '$lib/format';

	import { categoryRows, combineTones, toneRows, type ToneCounts } from '$lib/digest-stats';
	import { formatDisplayDateTime, formatDisplayDateTimeAt } from '$lib/format';
	import type { DailySummaryContent, DigestNewsItem } from '$lib/api';

	let {
		content,
		tones = null,
		sentimentByEvent = {},
		fieldCount = 0,
		updatedAt = null
	}: {
		content: DailySummaryContent;
		/** Media/social sentiment split for the day; null when the query failed. */
		tones?: { media: ToneCounts; social: ToneCounts } | null;
		/** Majority sentiment per event id, keyed as string. Empty when unknown. */
		sentimentByEvent?: Record<string, string>;
		/** Field-data mentions for the day; the section hides at zero. */
		fieldCount?: number;
		/** Summary last update, rendered in the rectora stamp. */
		updatedAt?: string | null;
	} = $props();

	const noticias = $derived(content.noticias ?? []);

	const SOCIAL_SOURCES = new Set(['x_twitter', 'facebook_page']);
	/** Same chain anatomy as the feed cards: tipo · outlets. */
	function newsChannel(item: DigestNewsItem): string {
		if (!item.sources?.length) return 'Fuente no registrada';
		const first = item.sources[0];
		const parts: string[] = [
			SOCIAL_SOURCES.has(first.source) ? 'Redes sociales' : 'Noticias'
		];
		for (const s of item.sources) {
			try {
				const host = new URL(s.url).hostname.replace(/^www\./, '');
				const root = host.split('.').shift() ?? host;
				parts.push(root.length < 3 ? host : root);
			} catch {
				parts.push(s.source);
			}
		}
		return [...new Set(parts)].join(' · ');
	}
	const rectora = $derived(content.rectora ?? {});
	const redes = $derived(Object.entries(content.redes ?? {}));
	const personas = $derived(content.personas ?? []);
	const pendientes = $derived(content.pendientes ?? []);
	const gaps = $derived(content.coverage?.gaps ?? []);
	const total = $derived(content.coverage?.total ?? noticias.length);

	/** Topic taxonomy v2 size (classification-v2); legacy keys excluded. */
	const TOPIC_TOTAL = 9;

	const byTopic = $derived.by(() => {
		if (content.coverage?.by_topic) return content.coverage.by_topic;
		const counts: Record<string, number> = {};
		for (const item of noticias) if (item.topic) counts[item.topic] = (counts[item.topic] ?? 0) + 1;
		return Object.keys(counts).length > 0 ? counts : undefined;
	});
	const categories = $derived(categoryRows(byTopic, content.coverage?.total));
	const activeTopics = $derived(byTopic ? Object.keys(byTopic).length : 0);

	const mediaToneRows = $derived(toneRows(tones?.media, 'Sin calcular'));
	const socialToneRows = $derived(toneRows(tones?.social, 'Sin datos'));
	const overallTones = $derived(tones ? combineTones(tones.media, tones.social) : null);

	const redesMeta = $derived(
		redes.length > 0
			? redes
					.map(
						([source, info]) =>
							`${sourceLabel(source)}: ${info.count > 0 ? info.count : 'sin menciones'}`
					)
					.join(' · ')
			: 'Fuente sin conexión'
	);

	/** Rectora display name: content stamp first, persona lookup for pre-stamp digests. */
	const rectoraPersona = $derived(
		rectora.person_id ? personas.find((person) => person.person_id === rectora.person_id) : undefined
	);
	const rectoraName = $derived(rectora.name ?? rectoraPersona?.name ?? 'Rectora');
	/** Role · org note: content stamp wins, persona chain fallback, generic label last. */
	const rectoraRoleOrg = $derived.by(() => {
		const parts = [rectora.role ?? rectoraPersona?.role, rectora.org ?? rectoraPersona?.org].filter(
			(part): part is string => Boolean(part)
		);
		return parts.length > 0 ? parts.join(' · ') : null;
	});

	/* Home feed filters (mockup: Todo / Noticias / Redes). Digest items are
	   news-channel only, so the social filter renders the empty state. */
	let feedFilter = $state<'all' | 'news' | 'social'>('all');
	const FEED_FILTERS = [
		{ key: 'all', label: 'Todo' },
		{ key: 'news', label: 'Noticias' },
		{ key: 'social', label: 'Redes' }
	] as const;

	/* Tono pills: majority sentiment per event (sentimentByEvent); single-select,
	   active pill toggles off. Items without a resolvable tone only show unfiltered. */
	const TONE_FILTERS = [
		{ key: 'positive', label: 'Positivo' },
		{ key: 'neutral', label: 'Neutro' },
		{ key: 'negative', label: 'Negativo' }
	] as const;
	type ToneFilter = (typeof TONE_FILTERS)[number]['key'];
	let toneFilter = $state<null | ToneFilter>(null);

	const itemTone = (item: DigestNewsItem): string | null =>
		item.event_id !== undefined && item.event_id !== null
			? (sentimentByEvent[String(item.event_id)] ?? null)
			: null;

	const visibleNews = $derived.by(() => {
		if (feedFilter === 'social') return [];
		if (!toneFilter) return noticias;
		return noticias.filter((item) => itemTone(item) === toneFilter);
	});
	const newsStamp = $derived.by(() => {
		const raw = content.date ?? (updatedAt ? updatedAt.slice(0, 10) : null);
		if (!raw) return null;
		const date = new Date(`${raw}T00:00:00`);
		if (Number.isNaN(date.getTime())) return null;
		return date.toLocaleDateString('es-MX', { day: '2-digit', month: '2-digit', year: 'numeric' });
	});

	const sentimentedActions = $derived((rectora.actions ?? []).filter((action) => action.sentiment));
	const positiveShare = $derived.by(() => {
		if (sentimentedActions.length === 0) return null;
		const positive = sentimentedActions.filter((action) => action.sentiment === 'positive').length;
		return Math.round((positive / sentimentedActions.length) * 100);
	});

	/** Quotes: rectora news titles cited to their first source; actions as fallback. */
	const rectoraQuotes = $derived.by(() => {
		const fromNews = rectora.person_id
			? noticias
					.filter((item) => item.person_ids?.includes(rectora.person_id ?? -1) && item.title)
					.slice(0, 2)
					.map((item) => ({
						text: item.title ?? '',
						cite: item.sources[0]
							? `${sourceLabel(item.sources[0].source)} · titular de la nota`
							: 'Resumen del día'
					}))
			: [];
		if (fromNews.length > 0) return fromNews;
		return (rectora.actions ?? [])
			.filter((action) => action.title)
			.slice(0, 2)
			.map((action) => ({ text: action.title ?? '', cite: 'Resumen del día' }));
	});
</script>

<section id="cobertura" class="section" aria-labelledby="resumen-general">
	<div class="section-heading">
		<h2 id="resumen-general">Resumen general</h2>
		<span class="section-note">Medios y redes sociales</span>
	</div>
	<div class="summary-grid">
		<article class="summary-box" aria-labelledby="media-tone">
			<h3 id="media-tone">Tendencia en medios</h3>
			<p class="summary-meta">{total} {total === 1 ? 'nota registrada' : 'notas registradas'}</p>
			<dl class="tone-list" aria-label="Distribución de tono en medios">
				{#each mediaToneRows as row (row.key)}
					<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
				{/each}
				{#if tones && tones.media.unclassified > 0}
					<div><dt>Sin clasificar</dt><dd>{tones.media.unclassified}</dd></div>
				{/if}
			</dl>
			<p class="summary-note">
				{tones
					? 'Corresponde a las menciones de medios registradas en la ventana del día.'
					: 'La distribución de tono no estuvo disponible en esta consulta.'}
			</p>
		</article>
		<article class="summary-box" aria-labelledby="social-tone">
			<h3 id="social-tone">Tendencia en redes</h3>
			<p class="summary-meta">{redesMeta}</p>
			<dl class="tone-list" aria-label="Distribución de tono en redes sociales">
				{#each socialToneRows as row (row.key)}
					<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
				{/each}
				{#if tones && tones.social.unclassified > 0}
					<div><dt>Sin clasificar</dt><dd>{tones.social.unclassified}</dd></div>
				{/if}
			</dl>
			<p class="summary-note">
				{tones
					? 'Las publicaciones sociales se cuentan aparte de las notas de medios.'
					: 'El tono por red no estuvo disponible en esta consulta.'}
			</p>
		</article>
		<article class="summary-box" aria-labelledby="trending">
			<h3 id="trending">Temas en tendencia</h3>
			<p class="summary-meta">Redes sociales</p>
			<p class="trend-empty" role="status">
				Aún no hay temas identificados. Aparecerán aquí cuando la fuente social publique
				tendencias.
			</p>
		</article>
	</div>
</section>

<section id="desglose-cobertura" class="section" aria-labelledby="cobertura-dia">
	<div class="section-heading">
		<h2 id="cobertura-dia">Cobertura del día</h2>
		<span class="section-note">Noticias · {total} {total === 1 ? 'nota' : 'notas'}</span>
	</div>
	<div class="coverage">
		<div class="metric">
			<span class="metric-label">Notas registradas</span>
			<strong class="metric-big">{total}</strong>
			<span class="metric-detail">en la jornada</span>
		</div>
		<div class="metric">
			<span class="metric-label">Categorías activas</span>
			<strong class="metric-big">{activeTopics}</strong>
			<span class="metric-detail">de {TOPIC_TOTAL} categorías posibles</span>
		</div>
		<div class="metric">
			<span class="metric-label">Tonos de la selección</span>
			{#if overallTones && overallTones.total > 0 && overallTones.positive > 0}
				<strong class="metric-big">
					{overallTones.positive}
					<span class="metric-unit">positivas</span>
				</strong>
				<span class="metric-detail">
					<span>{overallTones.negative} negativa{overallTones.negative === 1 ? '' : 's'}</span>
					<span>{overallTones.neutral} neutra{overallTones.neutral === 1 ? 'l' : 'les'}</span>
				</span>
			{:else}
				<strong class="metric-big">–</strong>
				<span class="metric-detail">distribución no disponible</span>
			{/if}
		</div>
	</div>
	{#each gaps as gap (gap)}
		<p class="breakdown-note">{gap}</p>
	{/each}
	<h3 class="breakdown-heading">Notas por categoría</h3>
	{#if categories.length === 0}
		<p class="breakdown-note">Sin categorías clasificadas para este día.</p>
	{:else}
		<ul class="category-breakdown" aria-label="Notas por categoría; una categoría por nota">
			{#each categories as row (row.key)}
				<li class="category-row">
					<span class="category-name">{topicLabel(row.key)}</span>
					<span class="category-track" aria-hidden="true">
						<span class="category-fill" style="width:{row.pct}%"></span>
					</span>
					<span class="category-value">{row.count} · {row.pct}&nbsp;%</span>
				</li>
			{/each}
		</ul>
	{/if}
</section>

{#if fieldCount > 0}
<section id="datos-campo" class="section" aria-labelledby="datos-campo-heading">
	<div class="section-heading">
		<h2 id="datos-campo-heading">Datos de campo</h2>
		<span class="section-note">Formularios y encuestas · carga manual</span>
	</div>
	<div class="manual-data-panel">
		<div>
			<span class="manual-data-status">Sin estudio publicado</span>
			<h3>Aún no hay resultados de campo</h3>
			<p>
				Cuando se valide la primera carga, aquí aparecerán el hallazgo principal, el instrumento
				utilizado y el periodo de recolección.
			</p>
		</div>
		<dl class="manual-data-meta" aria-label="Estado de los datos de campo">
			<div><dt>Última actualización</dt><dd>No disponible</dd></div>
			<div><dt>Instrumento</dt><dd>No registrado</dd></div>
			<div><dt>Muestra</dt><dd>No registrada</dd></div>
		</dl>
	</div>
	<p class="manual-data-note">
		Esta fuente se actualiza ocasionalmente y no forma parte del total de notas ni del feed en
		tiempo real.
	</p>
</section>
{/if}

<section id="rectora" class="section" aria-labelledby="rectora-heading">
	<div class="section-heading">
		<h2 id="rectora-heading">{rectoraName}</h2>
		<span class="section-note">{rectoraRoleOrg ?? 'Persona focal del resumen'}</span>
	</div>
	{#if updatedAt}
		<p class="rectora-update">
			Resumen actualizado el <time datetime={updatedAt}>{formatDisplayDateTimeAt(updatedAt)}</time>
		</p>
	{/if}
	{#if rectora.mention_count}
		<div class="rectora-summary" aria-label="Resumen de cobertura de la persona focal">
			<div class="rectora-stat">
				<strong>{rectora.mention_count}</strong>
				<span>menciones</span>
			</div>
			{#if positiveShare !== null}
				<div class="rectora-stat">
					<strong>{positiveShare}&nbsp;%</strong>
					<span>positivas</span>
				</div>
			{:else if rectora.tone}
				<div class="rectora-stat">
					<strong>{rectora.tone}</strong>
					<span>tono</span>
				</div>
			{/if}
		</div>
	{:else}
		<p class="breakdown-note">Sin menciones de la persona focal en la ventana.</p>
	{/if}
	{#if rectoraQuotes.length > 0}
		<div class="quotes">
			{#each rectoraQuotes as quote, i (i)}
				<blockquote>
					“{quote.text}”
					<cite>{quote.cite}</cite>
				</blockquote>
			{/each}
		</div>
	{/if}
	{#if rectora.watch}<p class="breakdown-note">Vigilar: {rectora.watch}</p>{/if}
	{#if rectora.gaps}<p class="breakdown-note">Gap: {rectora.gaps}</p>{/if}
</section>

<section id="noticias" class="section" aria-labelledby="noticias-heading">
	<div class="section-heading">
		<h2 id="noticias-heading">Feed de noticias</h2>
		<a class="feed-full-link" href="/feed">Ver feed completo →</a>
	</div>
	<p class="feed-intro">
		Noticias y publicaciones ordenadas por hora de llegada. Esta vista de ejemplo aún no recibe
		actualizaciones en tiempo real.
	</p>
	<div class="feed-toolbar">
		<div class="feed-filters" role="group" aria-label="Filtrar el feed por fuente">
			{#each FEED_FILTERS as filter (filter.key)}
				<button
					class="feed-filter"
					type="button"
					data-filter={filter.key}
					aria-pressed={feedFilter === filter.key}
					onclick={() => (feedFilter = filter.key)}
				>
					{filter.label}
				</button>
			{/each}
		</div>
		<div class="feed-filters" role="group" aria-label="Filtrar el feed por tono">
			{#each TONE_FILTERS as tone (tone.key)}
				<button
					class="feed-filter tone-{tone.key}"
					type="button"
					data-tone={tone.key}
					aria-pressed={toneFilter === tone.key}
					onclick={() => (toneFilter = toneFilter === tone.key ? null : tone.key)}
				>
					{tone.label}
				</button>
			{/each}
		</div>
		<span class="feed-status">
			{newsStamp ? `Muestra del ${newsStamp} · ` : ''}sin actualización automática
		</span>
	</div>
	{#if noticias.length === 0}
		<p class="breakdown-note">Sin noticias registradas ese día.</p>
	{:else if visibleNews.length === 0}
		{#if feedFilter === 'social'}
			<p class="breakdown-note" role="status">
				No hay publicaciones de redes cargadas en esta vista de ejemplo. Aparecerán aquí cuando
				se conecte la fuente.
			</p>
		{:else}
			<p class="breakdown-note" role="status">Ninguna nota coincide con los filtros activos.</p>
		{/if}
	{:else}
		<ol class="editorial-list feed-list" aria-label="Feed de noticias del día">
			{#each visibleNews as item, i (item.event_id ?? `i${i}`)}
				<li class="news-item" data-channel="news">
					<NewsEntry
						variant="card"
						channel={newsChannel(item)}
						sentimentClass={item.event_id ? (sentimentByEvent[String(item.event_id)] ?? null) : null}
						sentimentText={item.event_id && sentimentByEvent[String(item.event_id)]
							? sentimentLabel(sentimentByEvent[String(item.event_id)])
							: null}
						title={item.title ?? 'Sin título'}
						titleHref={item.sources[0]?.url ?? null}
						body={[
							item.summary ?? null,
							item.why_it_matters ? `Por qué importa: ${item.why_it_matters}` : null
						]
							.filter(Boolean)
							.join(' ')}
					>
						{#snippet footerLeft()}
							{#if item.repeat}<span class="text-meta">Reiteración</span>{/if}
							{#if item.topic}<span>Categoría · {topicLabel(item.topic)}</span>{/if}
						{/snippet}

						{#snippet footerRight()}
							{#if item.event_id}
								<a href={`/events/${item.event_id}`}>Evento #{item.event_id}</a>
							{:else}
								Sin evento relacionado
							{/if}
						{/snippet}
					</NewsEntry>
				</li>
			{/each}
		</ol>
	{/if}
</section>

{#if personas.length > 0}
	<section class="section" aria-labelledby="personas-heading">
		<div class="section-heading">
			<h2 id="personas-heading">Personas mencionadas</h2>
			<span class="section-note">Detectadas en la jornada</span>
		</div>
		<ul class="plain-list">
			{#each personas as person (person.person_id)}
				<li>
					<a href="/persons/{person.person_id}" class="person-link">{person.name}</a>
					{#if person.role || person.org}
						<span class="person-meta">
							{[person.role, person.org].filter(Boolean).join(' · ')}
						</span>
					{/if}
					{#if person.fact} — {person.fact}{/if}
				</li>
			{/each}
		</ul>
	</section>
{/if}

{#if pendientes.length > 0}
	<section id="pendientes" class="section" aria-labelledby="pendientes-heading">
		<div class="section-heading">
			<h2 id="pendientes-heading">Pendientes y silencios</h2>
			<span class="section-note">Seguimiento de cobertura</span>
		</div>
		<ul class="pending-list">
			{#each pendientes as pending (pending)}
				<li><span>{pending}</span><span>ventana de 24 h</span></li>
			{/each}
		</ul>
	</section>
{/if}
