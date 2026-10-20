<script lang="ts">
	import MentionCard from './MentionCard.svelte';
	import type { FeedGroup } from '$lib/grouping';

	interface Props {
		group: FeedGroup;
		keywordLabel?: string | null;
	}

	let { group, keywordLabel = null }: Props = $props();
</script>

{#each group.mentions as mention (mention.id)}
	<MentionCard
		{mention}
		{keywordLabel}
		event={group.event}
		coverageCount={group.mentions.length}
	/>
{/each}
