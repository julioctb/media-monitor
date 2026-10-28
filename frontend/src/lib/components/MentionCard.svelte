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
		/** Mentions in the same-event group (footer coverage chip). */
		coverageCount?: number;
	}

	let {
		mention,
		event = null,
		keywordLabel = null,
		coverageCount = 1
	}: Props = $props();

	const when = $derived(mention.published_at ?? mention.ingested_at);
	/** Channel label per mockup: tipo de fuente, not the raw tag. */
	const channelLabel = $derived(
		mention.source.startsWith('field')
			? 'Datos de campo'
			: isNewsSource(mention.source)
				? 'Noticias'
				: 'Redes sociales'
	);
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

	/** Link shorteners: the root split would print garbage like "t". */
	const SHORTENERS = new Set(['t.co', 'bit.ly', 'ow.ly', 'tinyurl.com', 'is.gd', 'buff.ly']);

	/** Second chain link: domain root for news (e-consulta), platform for social. */
	function outletFromUrl(url: string): string | null {
		try {
			const host = new URL(url).hostname.replace(/^www\./, '');
			const root = host.split('.').shift() ?? '';
			// Shorteners and 1-letter roots read broken; show the full host.
			if (root.length < 3 || SHORTENERS.has(host)) return host;
			return root;
		} catch {
			return null;
		}
	}

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
	titleHref={mention.url}
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
		{#if keywordLabel}<span>Palabra clave: {keywordLabel}</span>{/if}
		{#if event}
			<a class="event-chip" href={`/events/${event.id}`} title={event.title}>
				Evento #{event.id} · {coverageCount}
				{coverageCount === 1 ? 'cobertura' : 'coberturas'} del mismo evento
			</a>
		{/if}
	{/snippet}
</NewsEntry>
