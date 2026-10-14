<script lang="ts">
	import {
		classificationBadgeClass,
		classificationLabel,
		formatDisplayDateTime,
		sentimentBadgeClass,
		sentimentLabel,
		sourceLabel,
		topicBadgeClass,
		topicLabel
	} from '$lib/format';
	import type { Mention } from '$lib/api';

	/** Canonical event context, shown as a chip when the caller resolved it. */
	export interface MentionEventRef {
		id: number;
		title: string;
	}

	interface Props {
		mention: Mention;
		/** Event title when this mention belongs to a canonical event. */
		event?: MentionEventRef | null;
		/** Matched keyword text, when the mention is linked to one. */
		keywordLabel?: string | null;
	}

	let { mention, event = null, keywordLabel = null }: Props = $props();

	const when = $derived(mention.published_at ?? mention.ingested_at);
	/** The `*` marks ingest-date fallbacks (no published_at on the row). */
	const inferred = $derived(mention.published_at === null);
	const hasSummary = $derived(typeof mention.summary === 'string' && mention.summary.trim() !== '');
	const political = $derived(mention.classifications?.find((c) => c.classifier === 'political'));
	const topics = $derived(mention.classifications?.filter((c) => c.classifier === 'topic') ?? []);
	const headline = $derived(mention.title?.trim() || mention.url);
</script>

<article
	aria-labelledby={`mention-${mention.id}-title`}
	class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-slate-300"
>
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-500">
		<span
			class="inline-flex items-center rounded-full bg-slate-100 px-2 py-0.5 font-medium text-slate-600 ring-1 ring-inset ring-slate-500/20"
		>
			{`Fuente: ${sourceLabel(mention.source)}`}
		</span>
		<span
			class={`inline-flex items-center rounded-full px-2 py-0.5 font-medium ring-1 ring-inset ${sentimentBadgeClass(mention.sentiment)}`}
		>
			{`Sentimiento: ${mention.sentiment ? sentimentLabel(mention.sentiment) : sentimentLabel(null)}`}
		</span>
		<span class="tabular-nums">
			<time datetime={when}>{formatDisplayDateTime(when)}</time>{inferred ? '*' : ''}
		</span>
		{#if keywordLabel}
			<span>{`Palabra clave: ${keywordLabel}`}</span>
		{/if}
		{#if mention.reach !== null}
			<span class="tabular-nums">{`Alcance: ${mention.reach}`}</span>
		{/if}
	</div>

	<h3 id={`mention-${mention.id}-title`} class="mt-2 text-sm font-semibold text-slate-900">
		<a
			href={mention.url}
			target="_blank"
			rel="noopener noreferrer"
			aria-label={`${headline} (abre en una pestaña nueva)`}
			class="hover:underline"
		>
			{headline}
		</a>
	</h3>

	{#if mention.content?.trim()}
		<p class="mt-1 line-clamp-2 text-sm text-slate-600">{mention.content}</p>
	{/if}

	{#if event}
		<a
			href={`/events/${event.id}`}
			class="mt-2 inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-600/20 hover:bg-amber-100"
		>
			Evento: {event.title}
		</a>
	{/if}

	{#if political || topics.length > 0}
		<div class="mt-2 flex flex-wrap items-center gap-1">
			{#if political}
				<span
					class={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${classificationBadgeClass(political.label)}`}
				>
					{classificationLabel(political.label)}
				</span>
			{/if}
			{#each topics as topic (topic.label)}
				<span
					class={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${topicBadgeClass(topic.label)}`}
				>
					{topicLabel(topic.label)}
				</span>
			{/each}
		</div>
	{/if}

	{#if hasSummary}
		<details class="mt-2">
			<summary class="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
				Resumen del análisis
			</summary>
			<p class="mt-1 border-l-2 border-slate-200 pl-3 text-sm text-slate-700">{mention.summary}</p>
		</details>
	{/if}
</article>
