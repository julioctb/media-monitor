<script lang="ts">
	import {
		eventChipLabel,
		formatDisplayDateTime,
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
	const isPolitical = $derived(
		mention.classifications?.some((c) => c.classifier === 'political' && c.label === 'political') ??
			false
	);
	const topics = $derived(mention.classifications?.filter((c) => c.classifier === 'topic') ?? []);
	const headline = $derived(mention.title?.trim() || mention.url);

	const SENTIMENT_CLASS: Record<string, string> = {
		positive: 'positive',
		negative: 'negative',
		neutral: 'neutral'
	};
	const sentimentClass = $derived(
		mention.sentiment ? (SENTIMENT_CLASS[mention.sentiment] ?? 'neutral') : ''
	);
	const sentimentText = $derived(
		mention.sentiment ? sentimentLabel(mention.sentiment) : 'Sin clasificar'
	);
</script>

<article
	aria-labelledby={`mention-${mention.id}-title`}
	class="feed-card"
>
	<div class="item-top">
		<span class="item-channel">{sourceLabel(mention.source)}</span>
		<span class="sentiment {sentimentClass}">{sentimentText}</span>
	</div>

	<p class="item-meta">
		<time datetime={when}>{formatDisplayDateTime(when)}</time>{inferred ? '*' : ''}
		{#if keywordLabel}<span>· Palabra clave: {keywordLabel}</span>{/if}
		{#if mention.reach !== null}<span>· Alcance: {mention.reach}</span>{/if}
	</p>

	<h3 id={`mention-${mention.id}-title`} class="item-title">
		<a
			href={mention.url}
			target="_blank"
			rel="noopener noreferrer"
			aria-label={`${headline} (abre en una pestaña nueva)`}
		>
			{headline}
		</a>
	</h3>

	{#if mention.content?.trim()}
		<p class="item-summary">{mention.content}</p>
	{/if}

	<div class="item-footer">
		<div class="item-chips">
			{#if isPolitical}<span>Política</span>{/if}
			{#each (mention.persons ?? []) as person (person.id)}
				<a href={`/persons/${person.id}`} title="Ver persona">{person.name}</a>
			{/each}
			{#each topics as topic (topic.label)}
				<span class={`topic-chip ${topicBadgeClass(topic.label)}`}>{topicLabel(topic.label)}</span>
			{/each}
		</div>
		<span class="item-event">
			{#if event}
				<a href={`/events/${event.id}`} title={event.title}>{eventChipLabel(mention.title, event.title)}</a>
			{:else}
				Sin evento relacionado
			{/if}
		</span>
	</div>

	{#if typeof mention.summary === 'string' && mention.summary.trim() !== ''}
		<details class="mt-2">
			<summary class="cursor-pointer text-xs font-medium text-muted hover:text-ink">
				Resumen del análisis
			</summary>
			<p class="mt-1 border-l-2 border-line pl-3 text-sm text-ink-2">{mention.summary}</p>
		</details>
	{/if}
</article>

