<script lang="ts">
	/**
	 * Global toast outlet (mockup #toast): single message, `role=status`,
	 * fixed bottom-center. Mounted once from the root layout.
	 */
	import { toast } from '$lib/toast.svelte';
</script>

{#if toast.message}
	<p class="toast" role="status">{toast.message}</p>
{/if}
