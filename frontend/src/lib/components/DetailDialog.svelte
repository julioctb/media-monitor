<script lang="ts">
	import type { Snippet } from 'svelte';

	/**
	 * Shared detail-dialog chrome (mockup #detail-dialog + campo pattern).
	 * One owner of the head/close/body markup: pages compose the body via
	 * the children snippet. Opens when `open` turns truthy; jsdom-safe
	 * (no showModal there). The parent clears `open` on close.
	 */
	interface Props {
		/** aria id of the head title element. */
		titleId: string;
		/** Head title text. */
		title: string;
		/** Dialog opens while truthy (an id, an object, a boolean…). */
		open: unknown;
		/** Parent clears its open state here. */
		onclose?: () => void;
		/** Extra class for the dialog element (e.g. `mention-detail`). */
		variant?: string;
		/** Dialog body. */
		children?: Snippet;
	}

	let { titleId, title, open, onclose, variant = '', children }: Props = $props();
	let dialogEl: HTMLDialogElement | null = $state(null);

	$effect(() => {
		if (open && typeof dialogEl?.showModal === 'function') dialogEl.showModal();
	});
</script>

<dialog
	class="detail-dialog {variant}"
	bind:this={dialogEl}
	aria-labelledby={titleId}
	onclose={() => onclose?.()}
>
	<div class="dialog-head">
		<strong id={titleId}>{title}</strong>
		<button class="icon-button" type="button" onclick={() => dialogEl?.close()} aria-label="Cerrar detalle">
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12 M6 18 18 6" /></svg>
		</button>
	</div>
	<div class="dialog-body">
		{#if open}{@render children?.()}{/if}
	</div>
</dialog>
