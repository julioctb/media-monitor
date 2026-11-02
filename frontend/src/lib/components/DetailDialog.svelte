<script lang="ts">
	import type { Snippet } from 'svelte';
	import { ICON_PATHS } from '$lib/icons';

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
		/** Opt-in backdrop closing; existing dialogs retain native inert-backdrop behavior. */
		closeOnBackdrop?: boolean;
		/** Dialog body. */
		children?: Snippet;
	}

	let {
		titleId,
		title,
		open,
		onclose,
		variant = '',
		closeOnBackdrop = false,
		children
	}: Props = $props();
	let dialogEl: HTMLDialogElement | null = $state(null);
	let returnFocus: HTMLElement | null = null;

	$effect(() => {
		if (!dialogEl) return;
		if (open && !dialogEl.open && typeof dialogEl.showModal === 'function') {
			returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
			dialogEl.showModal();
		} else if (!open && dialogEl.open && typeof dialogEl.close === 'function') {
			// Parent-driven closure must close the native chrome as well.
			dialogEl.close();
		}
	});

	function finishClose() {
		onclose?.();
		if (returnFocus?.isConnected) returnFocus.focus();
		returnFocus = null;
	}

	function cancel(event: Event) {
		event.preventDefault();
		dialogEl?.close();
	}

	function backdrop(event: MouseEvent) {
		if (closeOnBackdrop && event.target === event.currentTarget) dialogEl?.close();
	}
</script>

<dialog
	class="detail-dialog {variant}"
	bind:this={dialogEl}
	aria-labelledby={titleId}
	onclose={finishClose}
	oncancel={cancel}
	onclick={backdrop}
>
	<div class="dialog-head">
		<strong id={titleId}>{title}</strong>
		<button class="icon-button" type="button" onclick={() => dialogEl?.close()} aria-label="Cerrar detalle">
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.close} /></svg>
		</button>
	</div>
	<div class="dialog-body">
		{#if open}{@render children?.()}{/if}
	</div>
</dialog>
