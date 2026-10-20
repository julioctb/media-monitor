<script lang="ts">
	import { sourceLabel, topicLabel } from '$lib/format';

	import { categoryRows, combineTones, toneRows, type ToneCounts } from '$lib/digest-stats';
	import { formatDisplayDateTime } from '$lib/format';
	import type { DailySummaryContent } from '$lib/api';

	let {
		content,
		tones = null,
		updatedAt = null
	}: {
		content: DailySummaryContent;
		/** Media/social sentiment split for the day; null when the query failed. */
		tones?: { media: ToneCounts; social: ToneCounts } | null;
		/** Summary last update, rendered in the rectora stamp. */
		updatedAt?: string | null;
	} = $props();

	const noticias = $derived(content.noticias ?? []);
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

	/** Rectora display name from the digest people section, when linked. */
	const rectoraPersona = $derived(
		rectora.person_id ? personas.find((person) => person.person_id === rectora.person_id) : undefined
	);
	const rectoraName = $derived(rectoraPersona?.name ?? 'Rectora');

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
			<span class="metric-label">Tonos del día</span>
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

<section id="rectora" class="section" aria-labelledby="rectora-heading">
	<div class="section-heading">
		<h2 id="rectora-heading">{rectoraName}</h2>
		<span class="section-note">
			{rectoraPersona
				? [rectoraPersona.role, rectoraPersona.org].filter(Boolean).join(' · ')
				: 'Persona focal del resumen'}
		</span>
	</div>
	{#if updatedAt}
		<p class="rectora-update">Resumen actualizado {formatDisplayDateTime(updatedAt)}</p>
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
		<h2 id="noticias-heading">Noticias del día</h2>
		<a class="feed-full-link" href="/feed">Ver feed completo →</a>
	</div>
	{#if noticias.length === 0}
		<p class="breakdown-note">Sin noticias registradas ese día.</p>
	{:else}
		<ul class="story-list">
			{#each noticias as item, i (item.event_id ?? `i${i}`)}
				<li class="story-card">
					<div class="story-top">
						<span class="story-channel">
							{item.sources.length > 0
								? item.sources.map((s) => sourceLabel(s.source)).join(' · ')
								: 'Fuente no registrada'}
						</span>
						{#if item.confidence}
							<span class="sentiment">Confianza {item.confidence}</span>
						{/if}
					</div>
					<h3 class="story-title">{item.title}</h3>
					{#if item.summary}<p class="story-summary">{item.summary}</p>{/if}
					{#if item.why_it_matters}
						<p class="story-why">Por qué importa: {item.why_it_matters}</p>
					{/if}
					<div class="story-footer">
						<div class="story-chips">
							{#if item.topic}<span>Categoría · {topicLabel(item.topic)}</span>{/if}
						</div>
						<span class="story-event">
							{item.event_id ? `Evento #${item.event_id}` : 'Sin evento relacionado'}
						</span>
					</div>
				</li>
			{/each}
		</ul>
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
