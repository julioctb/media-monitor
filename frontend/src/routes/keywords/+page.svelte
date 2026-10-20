<script lang="ts">
	import KeywordsPanel from '$lib/components/KeywordsPanel.svelte';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();
</script>

<svelte:head>
	<title>Palabras clave | Media Monitor</title>
</svelte:head>

<header class="page-head">
	<h1 class="page-title">Palabras clave</h1>
	<p class="lead">Términos monitoreados en noticias y redes. La misma tabla vive en Configuración.</p>
</header>

{#if form}
	<div
		role={form.ok ? 'status' : 'alert'}
		class={`mt-4 rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${
			form.ok
				? 'bg-success/10 text-success ring-success/30'
				: 'bg-danger/10 text-danger ring-danger/30'
		}`}
	>
		{form.message}
	</div>
{/if}

<section class="panel" aria-labelledby="keywords-title">
	<div class="panel-head">
		<h2 id="keywords-title" class="panel-title">Palabras clave</h2>
		<p class="panel-note">Términos que activan el monitoreo, asociados a su idioma.</p>
	</div>
	<KeywordsPanel keywords={data.keywords} actionBase="" form={form} />
</section>
