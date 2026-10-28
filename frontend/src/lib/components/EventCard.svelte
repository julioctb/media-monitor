<script lang="ts">
	import type { EventSummary } from '$lib/api';

	interface Props {
		event: EventSummary;
	}

	let { event }: Props = $props();
</script>

<!-- v3 event card («Panel de monitoreo», eventCard): mini-id, headline
	link, optional summary, counts footer. Fields the app does not track
	(priority, per-source types, follow) are intentionally absent. -->
<article class="event-card" aria-labelledby={`event-${event.id}-title`}>
	<div class="mini-id">
		<span>EVENTO #{event.id}</span>
	</div>

	<h3 id={`event-${event.id}-title`} class="headline">
		<a href={`/events/${event.id}`}>{event.title}</a>
	</h3>

	{#if event.summary?.trim()}
		<p class="event-summary">{event.summary}</p>
	{/if}

	<div class="event-card-footer">
		<span class="text-xs text-muted tabular-nums">
			{event.mention_count}
			{event.mention_count === 1 ? 'mención' : 'menciones'} ·
			{event.source_count}
			{event.source_count === 1 ? 'fuente' : 'fuentes'}
		</span>
	</div>
</article>
