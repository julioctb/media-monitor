<script lang="ts">
	import MentionCard from './MentionCard.svelte';
	import { formatDisplayDateTime, sourceLabel } from '$lib/format';
	import type { FeedGroup } from '$lib/grouping';

	interface Props {
		group: FeedGroup;
		keywordLabel?: string | null;
	}

	let { group, keywordLabel = null }: Props = $props();

	const rest = $derived(group.mentions.length > 1 ? group.mentions.slice(1) : []);
</script>

{#if rest.length === 0}
	<MentionCard mention={group.mentions[0]} {keywordLabel} event={null} />
{:else}
	<div class="space-y-2">
		<MentionCard mention={group.mentions[0]} {keywordLabel} event={group.event} />
		<details class="rounded-lg border border-slate-200 bg-slate-50/60">
			<summary class="cursor-pointer select-none px-3 py-2 text-xs font-medium text-slate-600 hover:text-slate-900">
				Otras {rest.length} {rest.length === 1 ? 'cobertura' : 'coberturas'} del mismo evento
			</summary>
			<ul class="divide-y divide-slate-100 px-3 pb-2">
				{#each rest as mention (mention.id)}
					<li class="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 py-1.5 text-xs">
						<span class="text-slate-500 tabular-nums">
							{formatDisplayDateTime(mention.published_at ?? mention.ingested_at)}
						</span>
						<span class="font-medium text-slate-700">{sourceLabel(mention.source)}</span>
						<a
							href={mention.url}
							target="_blank"
							rel="noopener noreferrer"
							class="text-slate-600 hover:underline"
						>
							{mention.title?.trim() || mention.url}
						</a>
					</li>
				{/each}
			</ul>
		</details>
	</div>
{/if}
