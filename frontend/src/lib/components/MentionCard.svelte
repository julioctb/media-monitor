<script lang="ts">
	import {
		channelLabelFor,
		formatDisplayDateTimeLong,
		outletFromUrl,
		sentimentLabel,
		topicBadgeClass,
		topicLabel
	} from '$lib/format';
	import { isNewsSource } from '$lib/digest-stats';
	import { ICON_PATHS } from '$lib/icons';
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
		/** Mentions in the same-event group (footer coverage chip). */
		coverageCount?: number;
		/** Opens the record-detail dialog (mockup headline-button). */
		onDetail?: (mention: Mention) => void;
		/** Opens the event-detail dialog instead of navigating (mockup data-event). */
		onEvent?: (event: MentionEventRef, coverageCount: number) => void;
	}

	let {
		mention,
		event = null,
		coverageCount = 1,
		onDetail,
		onEvent
	}: Props = $props();

	const when = $derived(mention.published_at ?? mention.ingested_at);
	const channelLabel = $derived(channelLabelFor(mention.source));
	/** Source chain per mockup: canal · medio · autor, as separate slots. */
	const sourceLabel = $derived.by(() => {
		if (isNewsSource(mention.source)) {
			const outlet = outletFromUrl(mention.url);
			if (outlet) return outlet;
			return null;
		}
		return PLATFORM_LABEL[mention.source] ?? null;
	});
	const author = $derived(mention.author?.trim() || null);

	/** Body: the editorial summary when enriched, else the article excerpt. */
	const body = $derived.by(() => {
		const summary = mention.summary?.trim();
		if (summary) return { text: summary, clamp: false };
		const content = mention.content?.trim();
		return content ? { text: content, clamp: true } : { text: null, clamp: false };
	});

	const PLATFORM_LABEL: Record<string, string> = {
		x_twitter: 'X',
		twitter: 'X',
		facebook: 'Facebook',
		facebook_page: 'Facebook',
		instagram: 'Instagram',
		youtube: 'YouTube',
		tiktok: 'TikTok'
	};
	const topics = $derived(mention.classifications?.filter((c) => c.classifier === 'topic') ?? []);
	const headline = $derived(mention.title?.trim() || mention.url);

	const SENTIMENT_CLASS: Record<string, string> = {
		positive: 'positive',
		negative: 'negative',
		neutral: 'neutral'
	};
	const sentimentClass = $derived(
		mention.sentiment ? (SENTIMENT_CLASS[mention.sentiment] ?? null) : null
	);
	const sentimentText = $derived(
		mention.sentiment ? sentimentLabel(mention.sentiment) : 'Sin clasificar'
	);
</script>

<NewsEntry
	channelLabel={channelLabel}
	sourceLabel={sourceLabel}
	author={author}
	sentimentClass={sentimentClass}
	sentimentText={sentimentText}
	publishedAt={when}
	publishedLabel={formatDisplayDateTimeLong(when)}
	title={headline}
	titleHref={onDetail ? null : mention.url}
	onTitle={onDetail ? () => onDetail(mention) : undefined}
	titleId={`mention-${mention.id}-title`}
	body={body.text}
	clampBody={body.clamp}
>
	{#snippet chips()}
		{#each topics as topic (topic.label)}
			<span class={`topic-chip ${topicBadgeClass(topic.label)}`}>{topicLabel(topic.label)}</span>
		{/each}
		{#each (mention.persons ?? []) as person (person.id)}
			<a href={`/persons/${person.id}`} title="Ver persona">{person.name}</a>
		{/each}
		{#if event}
			{#if onEvent}
				<button
					type="button"
					class="chip event-chip"
					onclick={() => onEvent(event, coverageCount)}
					title={event.title}
				>
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
						<path d={ICON_PATHS.layers} />
					</svg>
					Evento #{event.id} · {coverageCount}
					{coverageCount === 1 ? 'mención' : 'menciones'}
				</button>
			{:else}
				<a class="chip event-chip" href={`/events/${event.id}`} title={event.title}>
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
						<path d={ICON_PATHS.layers} />
					</svg>
					Evento #{event.id} · {coverageCount}
					{coverageCount === 1 ? 'mención' : 'menciones'}
				</a>
			{/if}
		{/if}
	{/snippet}
</NewsEntry>
