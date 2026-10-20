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
		teaser = null,
		detailsText = null,
		meta,
		note,
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
		/** 2-line body teaser (article excerpt); omitted when empty. */
		teaser?: string | null;
		/** Optional collapsible IA analysis text; hidden when null. */
		detailsText?: string | null;
		meta?: Snippet;
		note?: Snippet;
		footerLeft?: Snippet;
		footerRight?: Snippet;
	} = $props();
</script>

<article class={variant === 'card' ? 'feed-card' : 'feed-preview'} aria-labelledby={titleId}>
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

	{#if teaser}
		<p class="item-summary">{teaser}</p>
	{/if}

	{#if note}
		{@render note()}
	{/if}

	{#if footerLeft || footerRight}
		<div class="item-footer">
			<div class="item-chips">{@render footerLeft?.()}</div>
			<span class="item-event">{@render footerRight?.()}</span>
		</div>
	{/if}

	{#if detailsText}
		<details class="mt-1">
			<summary
				class="inline-flex min-h-11 cursor-pointer items-center py-1.5 pr-2 text-sm font-semibold text-ink underline decoration-line underline-offset-4 hover:decoration-ink"
			>
				Resumen del análisis
			</summary>
			<div
				class="rounded-(--radius-control) border border-line-soft bg-surface-warm px-4 py-3.5 text-sm leading-[1.5] text-ink-2"
			>
				{detailsText}
			</div>
		</details>
	{/if}
</article>
