<script lang="ts">
	import PersonsDetailDialog from '$lib/components/PersonsDetailDialog.svelte';
	import SourceBadge from '$lib/components/SourceBadge.svelte';
	import { BTN_PRIMARY_CLS } from '$lib/ui';
	import { ICON_PATHS } from '$lib/icons';
	import {
		channelClassFor,
		channelLabelFor,
		formatDirectoryDate,
		formatDisplayTime
	} from '$lib/format';
	import { prefs, seedPrefsFromServer } from '$lib/prefs';
	import type { PageProps } from './$types';
	import type { PersonDetail, PersonSummary } from '$lib/api';

	interface Props extends PageProps {
		/** Bridge override for view tests (isolated fixtures). */
		loadFicha?: (id: number) => Promise<PersonDetail>;
	}

	let { data, loadFicha }: Props = $props();

	// Single prefs seed: the store hydrates from the server-parsed cookie at
	// instance init, so the first paint already carries the follow state and
	// hydration matches SSR (same pattern as /events).
	// svelte-ignore state_referenced_locally
	seedPrefsFromServer(data.prefs);

	/** Mockup directoryResults: 25 identities per page. */
	const PAGE_SIZE = 25;

	type SortDir = 'asc' | 'desc';
	// The «Menciones» column is clickable (Julio: that column only; the
	// mockup's «Ordenar por» select was removed in its favor).
	let sortDir = $state<SortDir>('desc');
	let following = $state<'all' | 'followed'>('all');
	let page = $state(1);
	let openFichaId = $state<number | null>(null);
	// A new server payload (new query) restarts the visible window.
	$effect(() => {
		data.q;
		page = 1;
	});

	const followedIds = $derived($prefs.persons);
	const followedCount = $derived(
		data.persons.filter((person) => followedIds.includes(person.id)).length
	);

	// Client-side view over the loaded set (presentation only; the server
	// payload stays untouched). Ties break by name, like the mockup.
	const nameOrder = (a: PersonSummary, b: PersonSummary) => a.name.localeCompare(b.name, 'es');
	const sorted = $derived.by(() => {
		const list = [...data.persons];
		list.sort((a, b) => {
			const byMentions = b.mention_count - a.mention_count;
			return (sortDir === 'desc' ? byMentions : -byMentions) || nameOrder(a, b);
		});
		return list;
	});

	// Mockup directoryFiltered: the «En seguimiento» segment keeps only
	// followed identities over the current search/sort result.
	const filtered = $derived(
		following === 'followed'
			? sorted.filter((person) => followedIds.includes(person.id))
			: sorted
	);

	const pages = $derived(Math.max(1, Math.ceil(filtered.length / PAGE_SIZE)));
	const currentPage = $derived(Math.min(page, pages));
	const offset = $derived((currentPage - 1) * PAGE_SIZE);
	const visible = $derived(filtered.slice(offset, offset + PAGE_SIZE));

	function setFollowing(next: 'all' | 'followed') {
		following = next;
		page = 1;
	}

	function toggleMentionsSort() {
		sortDir = sortDir === 'asc' ? 'desc' : 'asc';
		page = 1;
	}

	// Fuentes badges: one per channel (Noticias/Redes sociales/Campo) in the
	// mockup's fixed order; labels come from the single channelLabelFor helper.
	const CHANNEL_ORDER = ['news', 'social', 'field'] as const;
	function personChannels(sources: string[] | undefined) {
		const out: { cls: (typeof CHANNEL_ORDER)[number]; label: string }[] = [];
		for (const cls of CHANNEL_ORDER) {
			const rep = (sources ?? []).find((source) => channelClassFor(source) === cls);
			if (rep) out.push({ cls, label: channelLabelFor(rep) });
		}
		return out;
	}

	function initials(name: string): string {
		return name
			.split(/\s+/)
			.filter(Boolean)
			.slice(0, 2)
			.map((word) => word[0]?.toUpperCase() ?? '')
			.join('');
	}
</script>

<svelte:head>
	<title>Personajes | Media Monitor</title>
</svelte:head>

<header class="persons-intro">
	<h1 class="page-title">Personajes</h1>
	<p>Quién aparece, en qué contexto y cómo evoluciona su presencia.</p>
</header>

<section class="directory-panel" aria-labelledby="persons-list-title">
	<div class="directory-header">
		<div>
			<h2 id="persons-list-title">Directorio de personajes</h2>
			<p role="status" aria-live="polite">
				{data.persons.length}
				{data.persons.length === 1 ? 'identidad detectada' : 'identidades detectadas'} ·
				{followedCount} en seguimiento
			</p>
		</div>
		<form method="get" role="search" class="directory-search">
			<span>Buscar por nombre</span>
			<span class="directory-search-row">
				<span class="search">
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
						<path d={ICON_PATHS.search} />
					</svg>
					<span class="sr-only">Buscar personajes por nombre o variante</span>
					<input
						type="search"
						id="q"
						name="q"
						value={data.q}
						placeholder="Nombre o variante…"
						autocomplete="off"
					/>
				</span>
				<button class={BTN_PRIMARY_CLS} type="submit">Buscar</button>
			</span>
		</form>
	</div>

	<div class="directory-toolbar">
		<div class="directory-segmented" role="group" aria-label="Filtrar por seguimiento">
			<button
				type="button"
				class={following === 'all' ? 'active' : ''}
				aria-pressed={following === 'all'}
				onclick={() => setFollowing('all')}
			>
				Todos
			</button>
			<button
				type="button"
				class={following === 'followed' ? 'active' : ''}
				aria-pressed={following === 'followed'}
				onclick={() => setFollowing('followed')}
			>
				En seguimiento
			</button>
		</div>
	</div>

	{#if data.persons.length === 0}
		{#if data.q}
			{@render directoryEmpty()}
		{:else}
			<div class="person-empty">
				<p class="empty">
					Sin personajes registrados todavía. Los personajes se detectan al enriquecer las
					menciones (protagonistas de cada nota).
				</p>
			</div>
		{/if}
	{:else if visible.length === 0}
		{@render directoryEmpty()}
	{:else}
		<div class="directory-result-heading">
			<p role="status" aria-live="polite">
				{filtered.length}
				{filtered.length === 1 ? 'identidad' : 'identidades'} ·
				{offset + 1}–{Math.min(offset + PAGE_SIZE, filtered.length)} visibles
			</p>
			<span>{PAGE_SIZE} por página</span>
		</div>
		<div class="directory-table-wrap">
			<table class="directory-table">
				<caption class="sr-only">
					Personajes detectados en las menciones. Los conteos corresponden al historial
					completo de cada identidad.
				</caption>
				<thead>
					<tr>
						<th scope="col">Identidad</th>
						<th scope="col">Tipo</th>
						<th scope="col" aria-sort={sortDir === 'asc' ? 'ascending' : 'descending'}>
							<button type="button" class="directory-sort" onclick={toggleMentionsSort}>Menciones</button>
						</th>
						<th scope="col">Fuentes</th>
						<th scope="col">Última aparición</th>
					</tr>
				</thead>
				<tbody>
					{#each visible as person (person.id)}
						{@const channels = personChannels(person.sources)}
						<tr>
							<td data-label="Nombre">
								<div class="directory-person-cell">
									<span class="directory-monogram" aria-hidden="true"
										>{initials(person.name)}</span
									>
									<div class="directory-person-copy">
										<a
											class="directory-name"
											href={`/persons/${person.id}`}
											onclick={(event) => {
												// Mockup: the row opens the «Ficha de identidad»
												// dialog; the href keeps the deep link (middle
												// click, new tab, no-JS).
												event.preventDefault();
												openFichaId = person.id;
											}}
										>
											{person.name}</a
										>
									</div>
								</div>
							</td>
							<td data-label="Tipo">Persona</td>
							<td data-label="Menciones"><strong>{person.mention_count}</strong></td>
							<td data-label="Fuentes">
								{#if channels.length}
									<div class="chips">
										{#each channels as channel (channel.cls)}
											<SourceBadge channelClass={channel.cls} label={channel.label} />
										{/each}
									</div>
								{:else}
									<span class="muted">—</span>
								{/if}
							</td>
							<td data-label="Última aparición">
								{#if person.last_seen_at}
									<time datetime={person.last_seen_at}>
										{formatDirectoryDate(person.last_seen_at)}
										<span class="directory-time"
											>{formatDisplayTime(person.last_seen_at)}</span
										>
									</time>
								{:else}
									<span class="missing">No disponible</span>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<div class="directory-pagination">
			<span>Página {currentPage} de {pages}</span>
			<div class="od-row">
				<button
					type="button"
					class="button"
					disabled={currentPage === 1}
					onclick={() => (page = currentPage - 1)}
				>
					Anterior
				</button>
				<button
					type="button"
					class="button"
					disabled={currentPage >= pages}
					onclick={() => (page = currentPage + 1)}
				>
					Siguiente
				</button>
			</div>
		</div>
	{/if}
</section>

<p class="directory-disclaimer">
	Los personajes se detectan automáticamente en el enriquecimiento de las notas; la columna
	«última aparición» refleja la última mención registrada.
</p>
<details class="directory-method">
	<summary>Cómo se organiza este directorio</summary>
	<p>
		Los conteos representan registros que mencionan a la persona, no repeticiones de su nombre
		dentro del mismo texto. Cada ficha mantiene el historial completo de menciones.
	</p>
</details>

{#snippet directoryEmpty()}
	<!-- Mockup directoryResults empty state minus its «Limpiar filtros» button
	     (Julio, L28): the search field and the Todos segment stay visible above,
	     so the button was redundant. -->
	<div class="empty">
		<h3>No hay identidades con estos filtros</h3>
		<p>Prueba otro nombre o amplía los filtros. El ejemplo actual solo contiene organizaciones.</p>
	</div>
{/snippet}

<PersonsDetailDialog personId={openFichaId} onclose={() => (openFichaId = null)} {loadFicha} />
