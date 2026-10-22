<script lang="ts">
	import { page } from '$app/state';
	import EventCard from '$lib/components/EventCard.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	function scopeHref(scope: 'eco' | 'todas'): string {
		const params = new URLSearchParams(page.url.searchParams);
		params.set('scope', scope);
		return `${page.url.pathname}?${params.toString()}`;
	}

	const ecoCount = $derived(
		data.scope === 'eco'
			? data.events.length
			: data.events.filter((event) => event.mention_count >= 2).length
	);
</script>

<svelte:head>
	<title>Eventos | Media Monitor</title>
</svelte:head>

<header class="flex flex-wrap items-end justify-between gap-4">
	<div>
		<h1 class="page-title">Eventos</h1>
		<p class="lead">
			Cada evento agrupa las notas que cubren el mismo hecho, aunque sea en distintos medios. El
			<span class="font-medium">feed</span> muestra cada nota individual tal como entró. La vista
			<span class="font-medium">Con eco de medios</span> muestra solo los hechos que dos o más
			medios cubrieron — la cobertura merece seguimiento; los eventos con una sola nota, que son
			repetidos del feed, quedan disponibles en <span class="font-medium">Todas</span>.
		</p>
	</div>

	<!-- Scope toggle -->
	<div class="segmented" role="group" aria-label="Alcance de eventos">
		<a href={scopeHref('eco')} aria-current={data.scope === 'eco' ? 'page' : undefined}>
			Con eco de medios
		</a>
		<a href={scopeHref('todas')} aria-current={data.scope === 'todas' ? 'page' : undefined}>
			Todas
		</a>
	</div>
</header>

{#if data.events.length === 0}
	<div class="empty mt-6">
		{#if data.scope === 'eco'}
			<p class="font-medium text-ink">Ningún evento con eco de varios medios todavía.</p>
			<p class="mt-1">
				Cuando dos o más notas cubran el mismo hecho, aparecerá aquí. También
				puedes ver
				<a href={scopeHref('todas')} class="underline hover:text-ink">todas</a>.
			</p>
		{:else}
			<p class="font-medium text-ink">Sin eventos registrados todavía.</p>
			<p class="mt-1">
				Los eventos aparecen cuando la ingesta agrupa menciones del mismo suceso.
			</p>
		{/if}
	</div>
{:else}
	<p class="mt-4 text-sm text-muted" role="status" aria-live="polite">
		{data.events.length}
		{data.scope === 'eco' ? 'historias con cobertura de varios medios' : 'eventos'} ·
		{ecoCount} con eco de 2+ medios
	</p>
	<ul class="events" aria-label="Eventos">
		{#each data.events as event (event.id)}
			<li>
				<EventCard {event} />
			</li>
		{/each}
	</ul>
	<p class="sample-note">
		Los eventos se agrupan en cada ciclo de ingesta; los recuentos corresponden a los eventos
		cargados en esta vista.
	</p>
{/if}
