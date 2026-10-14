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

<div class="flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">Eventos</h1>
		<p class="mt-1 max-w-2xl text-sm text-slate-500">
			Cada evento agrupa las notas que cubren el mismo hecho, aunque sea en
			distintos medios — la vista de la historia completa. El
			<span class="font-medium">feed</span>, en cambio, lista cada nota
			individual tal como entró.
		</p>
	</div>

	<!-- Scope toggle: same pill language as the layout tab strip. -->
	<div
		role="group"
		aria-label="Alcance de eventos"
		class="flex items-center gap-1 rounded-full border border-slate-200 bg-white p-1 shadow-sm"
	>
		<a
			href={scopeHref('eco')}
			aria-current={data.scope === 'eco' ? 'true' : undefined}
			class={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
				data.scope === 'eco'
					? 'bg-slate-900 text-white'
					: 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
			}`}
		>
			Con eco de medios
		</a>
		<a
			href={scopeHref('todas')}
			aria-current={data.scope === 'todas' ? 'true' : undefined}
			class={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
				data.scope === 'todas'
					? 'bg-slate-900 text-white'
					: 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
			}`}
		>
			Todas
		</a>
	</div>
</div>

{#if data.events.length === 0}
	<div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
		{#if data.scope === 'eco'}
			<p class="text-sm font-medium text-slate-700">
				Ningún evento con eco de varios medios todavía.
			</p>
			<p class="mt-1 text-sm text-slate-500">
				Cuando dos o más notas cubran el mismo hecho, aparecerá aquí. También
				puedes ver
				<a href={scopeHref('todas')} class="underline hover:text-slate-700">todas</a>.
			</p>
		{:else}
			<p class="text-sm font-medium text-slate-700">Sin eventos registrados todavía.</p>
			<p class="mt-1 text-sm text-slate-500">
				Los eventos aparecen cuando la ingesta agrupa menciones del mismo suceso.
			</p>
		{/if}
	</div>
{:else}
	<p class="mt-4 text-xs text-slate-400">
		{data.events.length}
		{data.scope === 'eco' ? 'historias con cobertura de varios medios' : 'eventos'} ·
		{ecoCount} con eco de 2+ medios
	</p>
	<ul class="mt-3 grid gap-3 md:grid-cols-2" aria-label="Eventos">
		{#each data.events as event (event.id)}
			<li>
				<EventCard {event} />
			</li>
		{/each}
	</ul>
{/if}
