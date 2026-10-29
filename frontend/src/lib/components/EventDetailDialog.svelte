<script lang="ts">
	import DetailDialog from './DetailDialog.svelte';
	import { formatDisplayDateTimeLong, outletFromUrl } from '$lib/format';
	import { isNewsSource } from '$lib/digest-stats';
	import { ICON_PATHS } from '$lib/icons';
	import type { EventDetail, EventMention } from '$lib/api';

	/**
	 * Event detail dialog (mockup eventDetail): the "Expediente #id" popup
	 * behind every event chip. Honest counting callout + the corroborating
	 * records, each opening the record dialog ("Leer registro original").
	 */
	let {
		event,
		onRecord,
		onclose
	}: {
		event: EventDetail;
		onRecord?: (mention: EventMention) => void;
		onclose: () => void;
	} = $props();

	const titleId = $derived(`event-${event.id}-title`);

	/** Channel label per mockup badge(): tipo de fuente. */
	function channelLabel(source: string): string {
		return source.startsWith('field')
			? 'Datos de campo'
			: isNewsSource(source)
				? 'Noticias'
				: 'Redes sociales';
	}

	function metaLabel(mention: EventMention): string {
		const when = mention.published_at ? formatDisplayDateTimeLong(mention.published_at) : null;
		const outlet = isNewsSource(mention.source) ? (outletFromUrl(mention.url) ?? null) : null;
		return [outlet ?? mention.source, when].filter(Boolean).join(' · ');
	}
</script>

<DetailDialog
	variant="event-detail"
	{titleId}
	title={`Expediente #${event.id}`}
	open={true}
	{onclose}
>
	<div class="dialog-body">
		<p class="daily-dialog-eyebrow">Evento #{event.id}</p>
		<h2 id={titleId} class="daily-dialog-title">{event.title}</h2>
		{#if event.summary}
			<p>{event.summary}</p>
		{/if}
		<div class="daily-dialog-warning dialog-callout">
			{event.mention_count}
			{event.mention_count === 1 ? 'mención' : 'menciones'} ·
			{event.source_count}
			{event.source_count === 1 ? 'tipo de fuente' : 'tipos de fuente'}. Conteo de registros, no de
			confirmaciones independientes.
		</div>
		<div class="dialog-section">
			<h3>Fuentes y evidencias</h3>
			{#each event.mentions as mention (mention.id)}
				<div class="daily-dialog-record">
					<span class="source-badge">{channelLabel(mention.source)}</span>
					<h4>{mention.title?.trim() || mention.url}</h4>
					<p class="daily-dialog-meta">{metaLabel(mention)}</p>
					{#if onRecord}
						<button
							type="button"
							class="text-link"
							onclick={() => onRecord?.(mention)}
						>
							Leer registro original
							<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
								<path d={ICON_PATHS.arrow} />
							</svg>
						</button>
					{:else}
						<a class="text-link" href={mention.url} target="_blank" rel="noopener noreferrer">
							Leer registro original
							<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
								<path d={ICON_PATHS.arrow} />
							</svg>
						</a>
					{/if}
				</div>
			{/each}
		</div>
	</div>
</DetailDialog>
