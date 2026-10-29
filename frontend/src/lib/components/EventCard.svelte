<script lang="ts">
	import { ICON_PATHS } from '$lib/icons';
	import type { EventSummary } from '$lib/api';

	interface Props {
		event: EventSummary;
		/** Pressed state of the follow toggle (mockup data-follow). */
		following?: boolean;
		/** Toggles the follow state (mockup toggle('follow')). */
		onFollowToggle?: () => void;
	}

	let { event, following = false, onFollowToggle }: Props = $props();
</script>

<!-- v3 event card («Panel de monitoreo», eventCard): mini-id, headline
	link, optional summary, counts footer + follow toggle. Fields the app
	does not track (priority, per-source types) are intentionally absent. -->
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
			<!-- source_count counts distinct capture channels, never outlets; the
				title says so, the visible word stays the mockup's. -->
			<span title={`${event.source_count} ${event.source_count === 1 ? 'tipo' : 'tipos'} de canal con registros`}>
				{event.source_count}
				{event.source_count === 1 ? 'fuente' : 'fuentes'}
			</span>
		</span>
		{#if onFollowToggle}
			<!-- Visibility = onFollowToggle wiring; pressed state = following. -->
			<button
				type="button"
				class="button"
				class:primary={following}
				aria-pressed={following}
				onclick={onFollowToggle}
			>
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d={following ? ICON_PATHS.check : ICON_PATHS.bookmark} />
				</svg>
				{following ? 'Siguiendo' : 'Seguir evento'}
			</button>
		{/if}
	</div>
</article>
