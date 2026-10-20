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
	class="group flex h-full flex-col rounded-2xl border border-line-soft bg-white p-5 transition-colors hover:border-line"
>
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-meta">
		<span class="tabular-nums">{`${event.mention_count} ${event.mention_count === 1 ? 'mención' : 'menciones'}`}</span>
		<span aria-hidden="true">·</span>
		<span>{`${event.source_count} ${event.source_count === 1 ? 'fuente' : 'fuentes'}`}</span>
		<span aria-hidden="true">·</span>
		<span class="tabular-nums">
			Ultima detección:
			<time datetime={event.last_seen_at}>{formatDisplayDateTime(event.last_seen_at)}</time>
		</span>
	</div>

	<h3 id={`event-${event.id}-title`} class="mt-2 text-base font-semibold leading-snug text-ink">
		<!-- Hover underlines the title only, never the whole card. -->
		<a
			href={`/events/${event.id}`}
			class="decoration-transparent underline-offset-[3px] transition-[text-decoration-color] group-hover:decoration-ink"
		>
			{event.title}
		</a>
	</h3>

	{#if event.summary?.trim()}
		<p class="mt-1 line-clamp-3 text-sm text-ink-2">{event.summary}</p>
	{/if}

	<p class="mt-auto pt-2 text-xs text-meta">
		Primera detección:
		<time datetime={event.first_seen_at} class="tabular-nums">
			{formatDisplayDateTime(event.first_seen_at)}
		</time>
	</p>
</article>
