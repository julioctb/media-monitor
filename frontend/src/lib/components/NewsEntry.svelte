<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * Single news entry — the v3 card anatomy (`feed-item`, «Panel de
	 * monitoreo»): one meta row (source badge · outlet · author · tone ·
	 * timestamp), headline (dialog button, external link or plain text),
	 * optional clamped body and the chips footer. Shared by the feed and
	 * the home digest negative-news cards; every mention renders through
	 * here exactly once (via MentionCard).
	 */
	let {
		channelLabel,
		sourceLabel = null,
		author = null,
		sentimentClass = null,
		sentimentText = null,
		publishedAt = null,
		publishedLabel = null,
		title,
		titleHref = null,
		onTitle = undefined,
		titleId = undefined,
		body = null,
		clampBody = false,
		chips
	}: {
		/** Channel name for the leading source badge (Noticias/Redes/Datos de campo). */
		channelLabel: string;
		/** Outlet or platform; the second element of the source chain. */
		sourceLabel?: string | null;
		author?: string | null;
		/** Tone css key (positive|negative|neutral); the badge stays neutral when null. */
		sentimentClass?: string | null;
		sentimentText?: string | null;
		/** ISO timestamp for <time datetime>; the pill is omitted when null. */
		publishedAt?: string | null;
		publishedLabel?: string | null;
		title: string;
		/** External link for the headline (raw mentions). */
		titleHref?: string | null;
		/** Opens the record-detail dialog instead of navigating (mockup headline-button). */
		onTitle?: () => void;
		titleId?: string;
		/** Body text: enrichment summary or article excerpt. */
		body?: string | null;
		/** Clamp the body to two lines (raw-content fallback). */
		clampBody?: boolean;
		chips?: Snippet;
	} = $props();
</script>

<article class="feed-item" aria-labelledby={titleId}>
	<div class="feed-meta">
		<span class="source-badge">{channelLabel}</span>
		{#if sourceLabel}<span>{sourceLabel}</span>{/if}
		{#if author}<span class="feed-author">{author}</span>{/if}
		{#if sentimentClass && sentimentText}
			<span class={`tone-badge tone-${sentimentClass}`}>{sentimentText}</span>
		{:else if sentimentText}
			<span class="tone-badge">{sentimentText}</span>
		{/if}
		{#if publishedLabel}
			<time class="feed-time" datetime={publishedAt ?? undefined}>{publishedLabel}</time>
		{/if}
	</div>

	<h3 id={titleId} class="headline">
		{#if onTitle}
			<button type="button" class="headline-button" onclick={onTitle}>{title}</button>
		{:else if titleHref}
			<a
				href={titleHref}
				target="_blank"
				rel="noopener noreferrer"
				aria-label={`${title} (abre en una pestaña nueva)`}
			>
				{title}
			</a>
		{:else}
			{title}
		{/if}
	</h3>

	{#if body}
		<p class="feed-body" class:clamped={clampBody}>{body}</p>
	{/if}

	{#if chips}
		<div class="chips">{@render chips()}</div>
	{/if}
</article>
