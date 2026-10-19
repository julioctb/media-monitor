<script lang="ts">
	import { page } from '$app/state';

	import { BTN_PRIMARY_CLS } from '$lib/ui';
</script>

<svelte:head>
	<title>Error | Media Monitor</title>
</svelte:head>

<section class="mx-auto max-w-xl py-16 text-center">
	<p class="text-sm font-semibold text-meta">Error {page.status}</p>
	<h1 class="page-title mt-2 text-center">
		{page.error?.message ?? 'Algo salió mal'}
	</h1>
	<a href="/" class={`${BTN_PRIMARY_CLS} mt-6`}>Volver al inicio</a>
</section>
