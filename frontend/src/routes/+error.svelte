<script lang="ts">
	import { page } from '$app/state';
</script>

<svelte:head>
	<title>Error | Media Monitor</title>
</svelte:head>

<section class="mx-auto max-w-xl py-16 text-center">
	<p class="text-sm font-semibold text-slate-500">Error {page.status}</p>
	<h1 class="mt-2 text-2xl font-semibold tracking-tight text-slate-900">
		{page.error?.message ?? 'Algo salió mal'}
	</h1>
	<a
		href="/"
		class="mt-6 inline-flex items-center rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
	>
		Volver al inicio
	</a>
</section>
