<script lang="ts">
	import type { Mention } from '$lib/api';
	import type { MentionEventRef } from './MentionCard.svelte';
	import { formatDisplayDateTime, outletFromUrl, sourceLabel } from '$lib/format';

	interface Props {
		/** Mention to show; dialog content renders only when non-null. */
		mention: Mention | null;
		/** Canonical event the mention belongs to, if any. */
		event?: MentionEventRef | null;
		/** Parent clears its state when the dialog closes. */
		onclose?: () => void;
	}

	let { mention, event = null, onclose }: Props = $props();
	let dialogEl: HTMLDialogElement | null = $state(null);

	$effect(() => {
		// jsdom no implementa showModal; los navegadores reales sí (patrón campo/home).
		if (mention && typeof dialogEl?.showModal === 'function') dialogEl.showModal();
	});
</script>

<!-- Mockup recordDetail: badge, título, cadena de fuente, texto original,
     publicación externa y evento canónico — todo fiel al dato, sin inventar. -->
<dialog
	class="detail-dialog mention-detail"
	bind:this={dialogEl}
	aria-labelledby="mention-detail-title"
	{onclose}
>
	<div class="dialog-head">
		<strong id="mention-detail-title">Detalle de la mención</strong>
		<button
			type="button"
			class="icon-button"
			onclick={() => dialogEl?.close()}
			aria-label="Cerrar"
		>
			Cerrar
		</button>
	</div>
	<div class="dialog-body">
		{#if mention}
			<span class="source-badge">{sourceLabel(mention.source)}</span>
			<h2 class="daily-dialog-title">{mention.title?.trim() || mention.url}</h2>
			<p class="daily-dialog-meta">
				{outletFromUrl(mention.url) ?? 'Fuente sin dominio legible'}
				· {formatDisplayDateTime(mention.published_at ?? mention.ingested_at)}
			</p>
			{#if mention.author?.trim()}
				<p class="daily-dialog-meta">Autor: {mention.author}</p>
			{/if}
			<h3>Texto original</h3>
			{#if (mention.content ?? mention.summary)?.trim()}
				<div class="evidence-text">{mention.content ?? mention.summary}</div>
			{:else}
				<p class="daily-empty-note">Este registro no trae texto original en el corte.</p>
			{/if}
			<div class="dialog-actions">
				{#if mention.url}
					<a class="text-link" href={mention.url} target="_blank" rel="noreferrer">
						Ir a la publicación
					</a>
				{:else}
					<p class="daily-empty-note">No hay una publicación externa vinculada a este registro.</p>
				{/if}
				{#if event}
					<a class="text-link" href={`/events/${event.id}`}>Ver evento #{event.id}</a>
				{:else}
					<span class="source-badge">Todavía no forma un evento</span>
				{/if}
			</div>
		{/if}
	</div>
</dialog>
