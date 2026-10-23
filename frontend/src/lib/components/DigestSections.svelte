<script lang="ts">
	import { sourceLabel, topicLabel } from '$lib/format';

	import { focusPersonLabel, toneRows, type ToneCounts } from '$lib/digest-stats';
	import type { DailySummaryContent, DigestNewsItem } from '$lib/api';

	let {
		content,
		tones = null,
		sourcesCount = null,
		socialLabels = {}
	}: {
		content: DailySummaryContent;
		/** Day tone split media/social/field; null when /stats/day failed. */
		tones?: { media: ToneCounts; social: ToneCounts; field: ToneCounts } | null;
		/** Ingest sources wired for this client; null when settings unreadable. */
		sourcesCount?: number | null;
		 /** Label overrides for the redes block, built from settings. */
		socialLabels?: Record<string, string>;
	} = $props();

	const agenda = $derived(content.agenda ?? []);
	const activity = $derived(content.rectora?.activity ?? []);
	const pendientes = $derived(content.pendientes ?? []);
	const redes = $derived(Object.entries(content.redes ?? {}));

	const mediaTones = $derived(toneRows(tones?.media, 'Sin calcular'));
	const socialTones = $derived(toneRows(tones?.social, 'Sin datos'));
	const fieldTones = $derived(toneRows(tones?.field, 'Sin datos'));

	/** Sources note: real configured/always-on ingest sources, never a guess. */
	const sourcesNote = $derived(
		sourcesCount === null
			? 'fuentes activas'
			: `${sourcesCount} ${sourcesCount === 1 ? 'fuente activa' : 'fuentes activas'}`
	);

	/** Noticias grouped by topic, digest order preserved inside each group. */
	const newsByTopic = $derived.by(() => {
		const groups: { topic: string | null; items: DigestNewsItem[] }[] = [];
		const byKey = new Map<string, { topic: string | null; items: DigestNewsItem[] }>();
		for (const item of content.noticias ?? []) {
			const key = item.topic ?? '';
			let group = byKey.get(key);
			if (!group) {
				group = { topic: item.topic ?? null, items: [] };
				byKey.set(key, group);
				groups.push(group);
			}
			group.items.push(item);
		}
		return groups;
	});

	/** «Fuente: … Confianza: …» line; null when the item carries neither. */
	function sourceLine(item: DigestNewsItem): string | null {
		const parts: string[] = [];
		const labels = [...new Set((item.sources ?? []).map((source) => sourceLabel(source.source)))];
		if (labels.length > 0) parts.push(`Fuente: ${labels.join(' · ')}`);
		if (item.confidence) parts.push(`Confianza: ${item.confidence}`);
		return parts.length > 0 ? `${parts.join('. ')}.` : null;
	}

	/** Fixed line for a tracked source the day's revision found silent. */
	const REDES_EMPTY_NOTE = 'Sin novedades fechables en la ventana.';

	interface RedesEntry {
		key: string;
		label: string;
		note: string;
	}

	/**
	 * Redes narrativas: note when the digest carries one; the fixed
	 * silent-line for configured sources without data (x always, Facebook
	 * when pages are configured). Sources with data but no narrative and
	 * unconfigured silences render nothing (never a fabricated claim).
	 */
	const redesEntries = $derived.by(() => {
		const entries: RedesEntry[] = [];
		for (const [key, info] of redes) {
			const note = typeof info?.note === 'string' ? info.note.trim() : '';
			if (note) {
				entries.push({ key, label: socialLabels[key] ?? sourceLabel(key), note });
			} else if ((info?.count ?? 0) === 0 && (key === 'x' || (key === 'facebook_page' && socialLabels[key]))) {
				entries.push({ key, label: socialLabels[key] ?? sourceLabel(key), note: REDES_EMPTY_NOTE });
			}
		}
		return entries;
	});

	/** Detail h3: focus person when identified, generic label otherwise. */
	const rectoraHeading = $derived.by(() => {
		const name = focusPersonLabel(content);
		return name ? `Rectora ${name}` : 'Rectora';
	});

	const hasDetail = $derived(
		newsByTopic.length > 0 ||
			agenda.length > 0 ||
			activity.length > 0 ||
			pendientes.length > 0 ||
			redesEntries.length > 0
	);
</script>

<section id="cobertura" class="section" aria-labelledby="resumen-general-heading">
	<div class="section-heading">
		<h2 id="resumen-general-heading">Resumen general <span class="heading-soft">( Tendencia )</span></h2>
		<span class="section-note">{sourcesNote}</span>
	</div>
	<div class="summary-grid">
		<article class="summary-box" aria-labelledby="media-tone">
			<h3 id="media-tone">Noticias</h3>
			{#if tones}
				<p class="summary-meta">
					{tones.media.total}
					{tones.media.total === 1 ? 'nota registrada' : 'notas registradas'}
				</p>
			{/if}
			<dl class="tone-list" aria-label="Distribución de tono en medios">
				{#each mediaTones as row (row.key)}
					<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
				{/each}
				{#if tones && tones.media.unclassified > 0}
					<div><dt>Sin clasificar</dt><dd>{tones.media.unclassified}</dd></div>
				{/if}
			</dl>
			{#if tones}
				<p class="summary-note">
					Corresponde a las menciones de medios registradas en la ventana del día.
				</p>
			{/if}
		</article>
		<article class="summary-box" aria-labelledby="social-tone">
			<h3 id="social-tone">Redes Sociales</h3>
			{#if tones}
				<p class="summary-meta">
					{tones.social.total > 0
						? `${tones.social.total} ${tones.social.total === 1 ? 'publicación registrada' : 'publicaciones registradas'}`
						: 'Sin publicaciones registradas'}
				</p>
			{/if}
			<dl class="tone-list" aria-label="Distribución de tono en redes sociales">
				{#each socialTones as row (row.key)}
					<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
				{/each}
				{#if tones && tones.social.unclassified > 0}
					<div><dt>Sin clasificar</dt><dd>{tones.social.unclassified}</dd></div>
				{/if}
			</dl>
			{#if tones}
				<p class="summary-note">
					Las publicaciones sociales no se incluyen en las {tones.media.total} notas.
				</p>
			{/if}
		</article>
		<article class="summary-box" aria-labelledby="field-tone">
			<h3 id="field-tone">Datos de Campo</h3>
			{#if tones}
				<p class="summary-meta">
					{tones.field.total > 0
						? `${tones.field.total} ${tones.field.total === 1 ? 'registro cargado' : 'registros cargados'}`
						: 'Sin registros cargados'}
				</p>
			{/if}
			<dl class="tone-list" aria-label="Distribución de tono en datos de campo">
				{#each fieldTones as row (row.key)}
					<div><dt>{row.label}</dt><dd>{row.value}</dd></div>
				{/each}
				{#if tones && tones.field.unclassified > 0}
					<div><dt>Sin clasificar</dt><dd>{tones.field.unclassified}</dd></div>
				{/if}
			</dl>
			{#if tones}
				<p class="summary-note">
					{tones.field.total > 0
						? 'Registros cargados manualmente; no forman parte del total de notas.'
						: 'Sin estudio publicado. Esta fuente se actualiza ocasionalmente.'}
				</p>
			{/if}
		</article>
	</div>
</section>

{#if hasDetail}
	<section class="section daily-detail" aria-labelledby="daily-detail-heading">
		<header class="daily-detail-header">
			<h2 id="daily-detail-heading">Resumen detallado del día</h2>
			<p>Interpretación y seguimiento de la cobertura.</p>
		</header>
		{#if newsByTopic.length > 0}
			<div class="daily-detail-block">
				<h3>Noticias</h3>
				{#each newsByTopic as group, gi (`group-${gi}`)}
					<div class="daily-detail-item">
						<h4>{group.topic ? topicLabel(group.topic) : 'Sin categoría'}</h4>
						{#each group.items as item, ii (item.event_id ?? `item-${gi}-${ii}`)}
							<div class="daily-detail-entry">
								{#if item.summary || item.title}<p>{item.summary ?? item.title}</p>{/if}
								{#if sourceLine(item)}<p class="daily-detail-source">{sourceLine(item)}</p>{/if}
							</div>
						{/each}
					</div>
				{/each}
			</div>
		{/if}
		{#if agenda.length > 0}
			<div class="daily-detail-block">
				<h3>Agenda</h3>
				<ul class="daily-detail-list">
					{#each agenda as item, i (`agenda-${i}`)}
						<li>
							<strong>{[item.when, item.status].filter(Boolean).join(' · ')}</strong>
							{item.title}{item.source ? ` Fuente: ${item.source}` : ''}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
		{#if activity.length > 0}
			<div class="daily-detail-block">
				<h3>{rectoraHeading}</h3>
				<ul class="daily-detail-list">
					{#each activity as item, i (`activity-${i}`)}
						<li>
							<strong>{[item.when, item.status].filter(Boolean).join(' · ')}</strong>
							{item.text}{item.channel ? ` (${item.channel})` : ''}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
		{#if redesEntries.length > 0}
			<div class="daily-detail-block">
				<h3>Redes sociales</h3>
				{#each redesEntries as entry (entry.key)}
					<div class="daily-detail-item">
						<h4>{entry.label}</h4>
						<p>{entry.note}</p>
					</div>
				{/each}
			</div>
		{/if}
		{#if pendientes.length > 0}
			<div class="daily-detail-block">
				<h3>Limitaciones de cobertura</h3>
				<ul class="daily-detail-list">
					{#each pendientes as pending, i (`pending-${i}`)}
						<li>{pending}</li>
					{/each}
				</ul>
			</div>
		{/if}
	</section>
{/if}
