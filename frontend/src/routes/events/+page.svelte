<script lang="ts">
	import EventCard from '$lib/components/EventCard.svelte';
	import { ICON_PATHS } from '$lib/icons';
	import { prefs, seedPrefsFromServer, setFollow } from '$lib/prefs';
	import { notifyPersist } from '$lib/toast.svelte';
	import type { EventSummary } from '$lib/api';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	// Single prefs seed: the store hydrates from the server-parsed cookie at
	// instance init, so the first paint already carries the follow state and
	// hydration matches SSR. Intentionally once per instance (each navigation
	// re-seeds); the store itself owns later updates.
	// svelte-ignore state_referenced_locally
	seedPrefsFromServer(data.prefs);

	const followingIds = $derived($prefs.follow);

	/** Mockup toggle('follow'): optimistic store+cookie, seen seeded on follow. */
	function toggleFollow(id: number, next: boolean, lastSeenAt: string | null) {
		notifyPersist(setFollow(id, next, lastSeenAt));
	}

	// Mockup search (eventView): client-side over the loaded set, case-folded
	// exactly like the mockup (toLocaleLowerCase 'es'). EventSummary carries
	// id/title/summary only — no per-event source, topic or priority data to
	// match, so the«fuente» leg of the mockup placeholder is omitted.
	let query = $state('');

	const matches = $derived.by(() => {
		const term = query.trim().toLocaleLowerCase('es');
		if (!term) return data.events;
		return data.events.filter((event) =>
			`${event.id} ${event.title} ${event.summary ?? ''}`.toLocaleLowerCase('es').includes(term),
		);
	});

	// Mockup eventCards(): «En seguimiento» is the slice of matches present in
	// prefs.follow (cookie mm_prefs); the rest is «Otros eventos», which
	// collapses to the single «Eventos identificados» group while nothing is
	// followed. Presentation only — the load serves one full population.
	const followed = $derived(matches.filter((event) => followingIds.includes(event.id)));
	const others = $derived(matches.filter((event) => !followingIds.includes(event.id)));
</script>

<svelte:head>
	<title>Eventos | Media Monitor</title>
</svelte:head>

<header class="events-intro">
	<div>
		<h1 class="page-title">Eventos</h1>
		<p>De menciones dispersas a hechos con contexto y trazabilidad.</p>
	</div>
</header>

<div class="events-note">
	Los eventos reúnen menciones del mismo hecho. Cada fuente se conserva por separado; los
	registros no constituyen confirmación independiente.
</div>

<div class="events-toolbar">
	<label class="search events-search">
		<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
			<path d={ICON_PATHS.search} />
		</svg>
		<span class="sr-only">Buscar eventos</span>
		<!-- Bindings replace the mockup's value+listener pair: the list is
			filtered in place, never re-requested from the server. -->
		<input
			id="events-search"
			type="search"
			placeholder="Buscar por número o asunto…"
			autocomplete="off"
			bind:value={query}
		/>
	</label>
	<span id="events-count" class="text-xs text-muted tabular-nums" aria-live="polite">
		{matches.length} de {data.events.length} eventos
	</span>
</div>

<!-- Mockup eventCards: both groups render through one section snippet; they
	differ only in id, title and member events. -->
{#snippet eventGroup(id: string, title: string, events: EventSummary[])}
	<section class="events-group" aria-labelledby={`${id}-title`}>
		<h2 id={`${id}-title`}>
			{title}
			<span class="sub-count">{events.length}</span>
		</h2>
		<div class="section-grid">
			{#each events as event (event.id)}
				<EventCard
					{event}
					following={followingIds.includes(event.id)}
					onFollowToggle={() =>
						toggleFollow(event.id, !followingIds.includes(event.id), event.last_seen_at)}
				/>
			{/each}
		</div>
	</section>
{/snippet}

<div class="events-list">
	{#if matches.length === 0}
		<div class="events-empty">
			{#if data.events.length === 0}
				<h3>Sin eventos registrados todavía.</h3>
				<p>Los eventos aparecen cuando la ingesta agrupa menciones del mismo hecho.</p>
			{:else}
				<h3>No se encontraron eventos</h3>
				<p>Prueba con otro número o asunto.</p>
			{/if}
		</div>
	{:else}
		{#if followed.length > 0}
			{@render eventGroup('events-following', 'En seguimiento', followed)}
		{/if}
		{#if others.length > 0}
			{@render eventGroup(
				'events-other',
				followed.length > 0 ? 'Otros eventos' : 'Eventos identificados',
				others
			)}
		{/if}
	{/if}
</div>
