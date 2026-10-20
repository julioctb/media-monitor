<script lang="ts">
	import { formatDisplayDateTimeLong, sentimentLabel, topicBadgeClass, topicLabel } from '$lib/format';
	import { isNewsSource } from '$lib/digest-stats';
	import type { Mention } from '$lib/api';
	import NewsEntry from '$lib/components/NewsEntry.svelte';

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
		/** Mentions in the same-event group (footer coverage count). */
		coverageCount?: number;
	}

	let { mention, event = null, keywordLabel = null, coverageCount = 1 }: Props = $props();

	const when = $derived(mention.published_at ?? mention.ingested_at);
	/** Channel label per mockup: tipo de fuente, not the raw tag. */
	const channelLabel = $derived(
		mention.source.startsWith('field')
			? 'Datos de campo'
			: isNewsSource(mention.source)
				? 'Noticias'
				: 'Redes sociales'
	);
	/** Concrete outlet: news → URL host; social → author handle/page. */
	const sourceDetail = $derived.by(() => {
		if (!isNewsSource(mention.source)) {
			const author = mention.author?.trim();
			if (author) return author;
		}
		try {
			return new URL(mention.url).hostname.replace(/^www\./, '');
		} catch {
			return mention.author?.trim() ?? null;
		}
	});
	/** Body: the editorial summary when enriched, else the article excerpt. */
	const body = $derived.by(() => {
		const summary = mention.summary?.trim();
		if (summary) return { text: summary, clamp: false };
		const content = mention.content?.trim();
		return content ? { text: content, clamp: true } : { text: null, clamp: false };
	});
	const topics = $derived(mention.classifications?.filter((c) => c.classifier === 'topic') ?? []);
	const headline = $derived(mention.title?.trim() || mention.url);

	const SENTIMENT_CLASS: Record<string, string> = {
		positive: 'positive',
		negative: 'negative',
		neutral: 'neutral'
	};
	const sentimentClass = $derived(
		mention.sentiment ? (SENTIMENT_CLASS[mention.sentiment] ?? 'neutral') : 'neutral'
	);
	const sentimentText = $derived(
		mention.sentiment ? sentimentLabel(mention.sentiment) : 'Sin clasificar'
	);
</script>

<NewsEntry
	variant="card"
	channel={channelLabel}
	sourceDetail={sourceDetail}
	sentimentClass={sentimentClass}
	sentimentText={sentimentText}
	title={headline}
	titleHref={mention.url}
	titleId={`mention-${mention.id}-title`}
	body={body.text}
	clampBody={body.clamp}
>
	{#snippet meta()}
		<span class="item-when">{formatDisplayDateTimeLong(when)}</span>
		{#if keywordLabel}<span>· Palabra clave: {keywordLabel}</span>{/if}
	{/snippet}

	{#snippet footerLeft()}
		{#each topics as topic (topic.label)}
			<span class={`topic-chip ${topicBadgeClass(topic.label)}`}>{topicLabel(topic.label)}</span>
		{/each}
		{#each (mention.persons ?? []) as person (person.id)}
			<a href={`/persons/${person.id}`} title="Ver persona">{person.name}</a>
		{/each}
	{/snippet}

	{#snippet footerRight()}
		{#if event}
			<a href={`/events/${event.id}`} title={event.title}>
				Evento #{event.id} · {coverageCount}
				{coverageCount === 1 ? 'cobertura' : 'coberturas'} del mismo evento
			</a>
		{/if}
	{/snippet}
</NewsEntry>


