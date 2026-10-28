<script lang="ts">
	import MentionCard from './MentionCard.svelte';
	import type { MentionEventRef } from './MentionCard.svelte';
	import type { FeedGroup } from '$lib/grouping';
	import type { Mention } from '$lib/api';

	interface Props {
		group: FeedGroup;
		keywordLabel?: string | null;
		/** Opens the record-detail dialog (mockup recordDetail). */
		onDetail?: (mention: Mention, event: MentionEventRef | null) => void;
	}

	let { group, keywordLabel = null, onDetail }: Props = $props();

	function detailFor(mention: Mention) {
		onDetail?.(mention, group.event ?? null);
	}
</script>

{#each group.mentions as mention (mention.id)}
	<MentionCard
		{mention}
		{keywordLabel}
		event={group.event}
		coverageCount={group.mentions.length}
		onDetail={onDetail ? detailFor : undefined}
	/>
{/each}
