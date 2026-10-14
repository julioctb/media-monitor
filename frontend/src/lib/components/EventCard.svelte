<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';
	import type { EventSummary } from '$lib/api';

	interface Props {
		event: EventSummary;
	}

	let { event }: Props = $props();
</script>

<article
	aria-labelledby={`event-${event.id}-title`}
	class="flex h-full flex-col rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-slate-300"
>
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
		<span class="tabular-nums">{`${event.mention_count} ${event.mention_count === 1 ? 'mención' : 'menciones'}`}</span>
		<span aria-hidden="true">·</span>
		<span>{`${event.source_count} ${event.source_count === 1 ? 'fuente' : 'fuentes'}`}</span>
		<span aria-hidden="true">·</span>
		<span class="tabular-nums">
			Ultima detección:
			<time datetime={event.last_seen_at}>{formatDisplayDateTime(event.last_seen_at)}</time>
		</span>
	</div>

	<h3 id={`event-${event.id}-title`} class="mt-2 text-sm font-semibold text-slate-900">
		<a href={`/events/${event.id}`} class="hover:underline">{event.title}</a>
	</h3>

	{#if event.summary?.trim()}
		<p class="mt-1 line-clamp-3 text-sm text-slate-600">{event.summary}</p>
	{/if}

	<p class="mt-auto pt-2 text-xs text-slate-400">
		Primera detección:
		<time datetime={event.first_seen_at} class="tabular-nums">
			{formatDisplayDateTime(event.first_seen_at)}
		</time>
	</p>
</article>
