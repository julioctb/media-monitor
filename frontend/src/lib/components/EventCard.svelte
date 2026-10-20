<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';
	import type { EventSummary } from '$lib/api';

	interface Props {
		event: EventSummary;
	}

	let { event }: Props = $props();
</script>

<article class="event-card" aria-labelledby={`event-${event.id}-title`}>
	<p class="event-meta">
		<span>{`${event.mention_count} ${event.mention_count === 1 ? 'mención' : 'menciones'}`}</span>
		<span>{`${event.source_count} ${event.source_count === 1 ? 'fuente' : 'fuentes'}`}</span>
		<span>
			Última detección:
			<time datetime={event.last_seen_at}>{formatDisplayDateTime(event.last_seen_at)}</time>
		</span>
	</p>

	<h2 id={`event-${event.id}-title`}>
		<!-- Hover underlines the title only, never the whole card. -->
		<a href={`/events/${event.id}`}>{event.title}</a>
	</h2>

	{#if event.summary?.trim()}
		<p class="event-summary">{event.summary}</p>
	{/if}

	<p class="event-first">
		Primera detección:
		<time datetime={event.first_seen_at}>{formatDisplayDateTime(event.first_seen_at)}</time>
	</p>
</article>
