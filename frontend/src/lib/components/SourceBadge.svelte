<script lang="ts">
	import { CHANNEL_ICON } from '$lib/format';
	import { ICON_PATHS } from '$lib/icons';

	/**
	 * The mockup's badge(t) in ONE place: channel-colored chip with leading
	 * icon (Noticias/Redes sociales/Campo). Shared by the feed cards and the
	 * persons directory; without a channel it renders the plain source-badge
	 * variant (label only).
	 */
	let {
		channelClass = null,
		label
	}: {
		channelClass?: 'field' | 'news' | 'social' | null;
		label: string;
	} = $props();
</script>

<span class={`source-badge${channelClass ? ` ${channelClass}` : ''}`}>
	{#if channelClass}
		<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
			<path d={ICON_PATHS[CHANNEL_ICON[channelClass]]} />
		</svg>
	{/if}
	{label}
</span>
