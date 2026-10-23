<script lang="ts">
	import MentionCard from '$lib/components/MentionCard.svelte';
	import type { Mention } from '$lib/api';

	/**
	 * Noticias negativas: the SAME anatomy as the feed — each entry is a
	 * MentionCard over the day's real mention (single source of truth, zero
	 * duplicated card markup). The scan lives in digest-stats; this component
	 * only caps the display.
	 */
	let { mentions = [] }: { mentions?: Mention[] } = $props();

	/** Editorial cap: at most three cards; the count chip carries the total. */
	const VISIBLE_MAX = 3;
	const visible = $derived(mentions.slice(0, VISIBLE_MAX));
</script>

{#if visible.length > 0}
	<section class="negative-summary" aria-labelledby="negative-news-heading">
		<div class="negative-heading">
			<h2 id="negative-news-heading">Noticias negativas</h2>
			<span class="negative-count">
				{mentions.length}
				{mentions.length === 1 ? 'noticia' : 'noticias'}
			</span>
		</div>
		<div class="negative-list">
			{#each visible as mention (mention.id)}
				<MentionCard {mention} />
			{/each}
		</div>
		{#if mentions.length > visible.length}
			<p class="negative-context">
				Se muestran {visible.length} de {mentions.length} noticias negativas del día.
			</p>
		{/if}
	</section>
{/if}
