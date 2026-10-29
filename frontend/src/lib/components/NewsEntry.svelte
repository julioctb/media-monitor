<script lang="ts">
	import { ICON_PATHS } from '$lib/icons';
	import { CHANNEL_ICON } from '$lib/format';
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
		channelClass = null,
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
		saved = null,
		onSave = undefined,
		chips
	}: {
		/** Channel name for the leading source badge (Noticias/Redes/Datos de campo). */
		channelLabel: string;
		/** Channel css key (news|social|field) for the badge variant; base look when null. */
		channelClass?: 'news' | 'social' | 'field' | null;
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
		/** Saved state for the foot toggle (mockup icon-button.saved); null hides it. */
		saved?: boolean | null;
		/** Toggles the saved state (mockup data-save); its presence adds the foot. */
		onSave?: () => void;
		chips?: Snippet;
	} = $props();
</script>

<article class="feed-item" aria-labelledby={titleId}>
	<div class="feed-meta">
		<span class={`source-badge${channelClass ? ` ${channelClass}` : ''}`}>
			{#if channelClass}
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d={ICON_PATHS[CHANNEL_ICON[channelClass]]} />
				</svg>
			{/if}
			{channelLabel}
		</span>
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

	{#if onSave}
		<!-- Mockup feed-foot: chips left, save toggle right. -->
		<div class="feed-foot">
			{#if chips}<div class="chips">{@render chips()}</div>{/if}
			<button
				type="button"
				class="icon-button"
				class:saved={saved === true}
				aria-label={saved ? 'Quitar de guardados' : 'Guardar noticia'}
				aria-pressed={saved === true}
				onclick={onSave}
			>
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d={ICON_PATHS.bookmark} />
				</svg>
			</button>
		</div>
	{:else if chips}
		<div class="chips">{@render chips()}</div>
	{/if}
</article>
