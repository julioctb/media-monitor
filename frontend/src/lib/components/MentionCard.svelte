<script lang="ts">
	import {
		formatDisplayDateTime,
		eventChipLabel,
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
	const isPolitical = $derived(
		mention.classifications?.some((c) => c.classifier === 'political' && c.label === 'political') ??
			false
	);
	const topics = $derived(mention.classifications?.filter((c) => c.classifier === 'topic') ?? []);
	const headline = $derived(mention.title?.trim() || mention.url);

	const SENTIMENT_CHIP_CLS: Record<string, string> = {
		positive: 'border-success/40 bg-success/10 text-success',
		negative: 'border-danger/40 bg-danger/10 text-danger',
		neutral: 'border-line bg-surface text-muted'
	};

	function sentimentChipClass(value: string | null): string {
		return value
			? (SENTIMENT_CHIP_CLS[value] ?? 'border-line bg-surface text-muted')
			: 'border-line text-meta';
	}
</script>

<article
	aria-labelledby={`mention-${mention.id}-title`}
	class="rounded-2xl border border-line-soft bg-white p-5 transition-colors hover:border-line"
>
	<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-meta">
		<span class="rounded-full bg-surface px-2.5 py-1 font-medium text-ink-2">
			{`Fuente: ${sourceLabel(mention.source)}`}
		</span>
		<span
			class={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-medium ${sentimentChipClass(mention.sentiment)}`}
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

	<h3 id={`mention-${mention.id}-title`} class="mt-2 text-base font-semibold leading-snug text-ink">
		<a
			href={mention.url}
			target="_blank"
			rel="noopener noreferrer"
			aria-label={`${headline} (abre en una pestaña nueva)`}
			class="break-words underline decoration-line underline-offset-[3px] hover:decoration-ink"
		>
			{headline}
		</a>
	</h3>

	{#if mention.content?.trim()}
		<p class="mt-1 line-clamp-2 break-words text-sm text-ink-2">{mention.content}</p>
	{/if}

	{#if event}
		<a
			href={`/events/${event.id}`}
			title={event.title}
			class="mt-2 inline-flex items-center gap-1 rounded-full border border-accent/30 bg-accent/10 px-2.5 py-0.5 text-xs font-medium text-accent transition-colors hover:bg-accent/20"
		>
			{eventChipLabel(mention.title, event.title)}
		</a>
	{/if}

	{#if isPolitical || (mention.persons?.length ?? 0) > 0 || topics.length > 0}
		<div class="mt-2 flex flex-wrap items-center gap-1">
			{#if isPolitical}
				<span class="inline-flex items-center rounded-full border border-line bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-2">
					Política
				</span>
			{/if}
			{#each (mention.persons ?? []) as person (person.id)}
				<a
					href={`/persons/${person.id}`}
					class="inline-flex items-center rounded-full border border-line-soft bg-surface px-2.5 py-0.5 text-xs font-medium text-ink-2 transition-colors hover:border-accent/40 hover:text-accent"
					title="Ver persona"
				>
					{person.name}
				</a>
			{/each}
			{#each topics as topic (topic.label)}
				<span
					class={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${topicBadgeClass(topic.label)}`}
				>
					{topicLabel(topic.label)}
				</span>
			{/each}
		</div>
	{/if}

	{#if hasSummary}
		<details class="mt-2">
			<summary class="cursor-pointer text-xs font-medium text-muted hover:text-ink">
				Resumen del análisis
			</summary>
			<p class="mt-1 border-l-2 border-line pl-3 text-sm text-ink-2">{mention.summary}</p>
		</details>
	{/if}
</article>
