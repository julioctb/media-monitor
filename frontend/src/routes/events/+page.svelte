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

<header class="events-intro">
	<div>
		<h1 class="page-title">Eventos</h1>
		<p>
			Hechos agrupados a partir de las menciones captadas. «Con eco de medios» reúne los que
			dos o más fuentes cubrieron; «Todas» añade los que tienen una sola nota.
		</p>
	</div>

	<!-- Scope toggle: eco = cobertura de 2+ medios; el resto vive en Todas. -->
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
	<div class="events-empty">
		{#if data.scope === 'eco'}
			<h3>Ningún evento con eco de varios medios todavía.</h3>
			<p>
				Cuando dos o más notas cubran el mismo hecho, aparecerá aquí. También puedes ver
				<a href={scopeHref('todas')} class="underline hover:text-ink">todas</a>.
			</p>
		{:else}
			<h3>Sin eventos registrados todavía.</h3>
			<p>Los eventos aparecen cuando la ingesta agrupa menciones del mismo suceso.</p>
		{/if}
	</div>
{:else}
	<p class="text-xs text-muted tabular-nums" role="status" aria-live="polite">
		{data.events.length}
		{data.scope === 'eco' ? 'historias con cobertura de varios medios' : 'eventos'} ·
		{ecoCount} con eco de 2+ medios
	</p>
	<ul class="events-list" aria-label="Eventos">
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
