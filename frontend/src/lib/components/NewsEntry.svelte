<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * Single news entry — the shared anatomy for every news card:
	 * top row (channel + sentiment), optional meta line, title, optional
	 * teaser, caller-provided footer halves and optional collapsed details.
	 * variant 'card' = boxed (feed); 'row' = divided list row (digest home).
	 */
	let {
		variant = 'card',
		channel,
		sentimentClass = null,
		sentimentText = null,
		title,
		titleHref = null,
		titleId = undefined,
		body = null,
		clampBody = false,
		meta,
		footerLeft,
		footerRight
	}: {
		variant?: 'card' | 'row';
		channel: string;
		/** Sentiment css key (positive|negative|neutral); pill hidden when null. */
		sentimentClass?: string | null;
		sentimentText?: string | null;
		title: string;
		titleHref?: string | null;
		titleId?: string;
		/** Body text: enrichment summary or article excerpt. */
		body?: string | null;
		/** Clamp the body to two lines (raw-content fallback). */
		clampBody?: boolean;
		meta?: Snippet;
		footerLeft?: Snippet;
		footerRight?: Snippet;
	} = $props();
</script>

<article
	class="{variant === 'card' ? 'feed-card' : 'feed-preview'}"
	class:accent-negative={sentimentClass === 'negative'}
	aria-labelledby={titleId}
>
	<div class="item-top">
		<span class="item-channel">{channel}</span>
		{#if sentimentClass && sentimentText}
			<span class="sentiment {sentimentClass}">{sentimentText}</span>
		{/if}
	</div>

	{#if meta}
		<p class="item-meta">{@render meta()}</p>
	{/if}

	<h3 id={titleId} class="item-title">
		{#if titleHref}
			<a href={titleHref} target="_blank" rel="noopener noreferrer" aria-label={`${title} (abre en una pestaña nueva)`}>
				{title}
			</a>
		{:else}
			{title}
		{/if}
	</h3>

	{#if body}
		<p class="item-summary" class:clamped={clampBody}>{body}</p>
	{/if}

	{#if footerLeft || footerRight}
		<div class="item-footer">
			<div class="item-chips">{@render footerLeft?.()}</div>
			<span class="item-event">{@render footerRight?.()}</span>
		</div>
	{/if}
</article>
