<script lang="ts">
	import EventCard from '$lib/components/EventCard.svelte';
	import { ICON_PATHS } from '$lib/icons';
	import { prefs, seedPrefsFromServer, setFollow } from '$lib/prefs';
	import { notifyPersist } from '$lib/toast.svelte';
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

	// Mockup search (eventView): client-side over the loaded set. EventSummary
	// carries id/title/summary only — no per-event source, topic or priority
	// data to match, so the«fuente» leg of the mockup placeholder is omitted.
	let query = $state('');

	const matches = $derived.by(() => {
		const term = query.trim().toLowerCase();
		if (!term) return data.events;
		return data.events.filter((event) =>
			`${event.id} ${event.title} ${event.summary ?? ''}`.toLowerCase().includes(term),
		);
	});

	// The mockup splits «En seguimiento» vs rest by a persisted follow state the
	// app does not track; the honest proxy is the coverage axis the load itself
	// is built on: eco = the story reached two or more sources. Single-source
	// events land in the mockup's «Otros eventos» / «Eventos identificados»
	// group, exactly its fallback when nothing is followed.
	const withEcho = $derived(matches.filter((event) => event.source_count >= 2));
	const withoutEcho = $derived(matches.filter((event) => event.source_count < 2));
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

<div class="aside-note events-note">
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
		{#if withEcho.length > 0}
			<section class="events-group" aria-labelledby="events-echo-title">
				<h2 id="events-echo-title">
					Con eco de medios <span class="sub-count">{withEcho.length}</span>
				</h2>
				<div class="section-grid">
					{#each withEcho as event (event.id)}
						<EventCard
							{event}
							following={followingIds.includes(event.id)}
							onFollowToggle={() =>
								toggleFollow(event.id, !followingIds.includes(event.id), event.last_seen_at)}
						/>
					{/each}
				</div>
			</section>
		{/if}
		{#if withoutEcho.length > 0}
			<section class="events-group" aria-labelledby="events-other-title">
				<h2 id="events-other-title">
					{withEcho.length > 0 ? 'Otros eventos' : 'Eventos identificados'}
					<span class="sub-count">{withoutEcho.length}</span>
				</h2>
				<div class="section-grid">
					{#each withoutEcho as event (event.id)}
						<EventCard
							{event}
							following={followingIds.includes(event.id)}
							onFollowToggle={() =>
								toggleFollow(event.id, !followingIds.includes(event.id), event.last_seen_at)}
						/>
					{/each}
				</div>
			</section>
		{/if}
	{/if}
</div>
