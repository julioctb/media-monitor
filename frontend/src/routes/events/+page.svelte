<script lang="ts">
	import EventCard from '$lib/components/EventCard.svelte';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();
</script>

<svelte:head>
	<title>Eventos | Media Monitor</title>
</svelte:head>

<div class="flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">Eventos canónicos</h1>
		<p class="mt-1 text-sm text-slate-500">
			Grupos de menciones que cubren el mismo hecho, ordenados por última detección.
		</p>
	</div>
</div>

{#if data.events.length === 0}
	<div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
		<p class="text-sm font-medium text-slate-700">Sin eventos registrados todavía.</p>
		<p class="mt-1 text-sm text-slate-500">
			Los eventos aparecen cuando la ingesta agrupa menciones del mismo suceso.
		</p>
	</div>
{:else}
	<ul class="mt-6 grid gap-3 md:grid-cols-2" aria-label="Eventos">
		{#each data.events as event (event.id)}
			<li>
				<EventCard {event} />
			</li>
		{/each}
	</ul>
{/if}
