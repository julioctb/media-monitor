<script lang="ts">
	import PersonDetailDialog from '$lib/components/PersonDetailDialog.svelte';
	import SourceBadge from '$lib/components/SourceBadge.svelte';
	import { monogram } from '$lib/digest-stats';
	import { PERSONS_PAGE_SIZE } from '$lib/persons';
	import { ICON_PATHS } from '$lib/icons';
	import {
		channelClassFor,
		channelLabelFor,
		formatDirectoryDate,
		formatDisplayTime
	} from '$lib/format';
	import { prefs, seedPrefsFromServer } from '$lib/prefs';
	import type { PageProps } from './$types';
	import type { PersonSummary } from '$lib/api';

	let { data }: PageProps = $props();
	// Single prefs seed: the store hydrates from the server-parsed cookie at
	// instance init, so the first paint already carries the follow state and
	// hydration matches SSR (same pattern as /events).
	// svelte-ignore state_referenced_locally
	seedPrefsFromServer(data.prefs);

	/** Mockup directoryResults: 25 identities per page. */
	const PAGE_SIZE = PERSONS_PAGE_SIZE;

	type SortDir = 'asc' | 'desc';
	// The «Menciones» column is clickable (Julio: that column only; the
	// mockup's «Ordenar por» select was removed in its favor).
	let sortDir = $state<SortDir>('desc');
	let following = $state<'all' | 'followed'>('all');
	let page = $state(1);
	let selected = $state<PersonSummary | null>(null);
	let filtersOpen = $state(false);
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

</script>

<svelte:head>
	<title>Personajes | Media Monitor</title>
</svelte:head>

<header class="page-header">
	<h1>Personajes</h1>
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
		<form method="get" role="search" class="directory-search-form">
			<label class="directory-search" for="directory-search">
				<span>Buscar por nombre</span>
				<span class="search">
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.search} /></svg>
					<input id="directory-search" type="search" name="q" value={data.q} placeholder="Nombre o variante…" autocomplete="off" />
				</span>
			</label>
		</form>
	</div>

	<div class="directory-toolbar">
		<button type="button" class="directory-filter-toggle" aria-controls="directory-productive-filters"
			aria-expanded={filtersOpen} onclick={() => (filtersOpen = !filtersOpen)}>Filtrar</button>
		<div id="directory-productive-filters" class="directory-filters directory-productive-filters" class:is-open={filtersOpen}>
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
		<button type="button" class="directory-mobile-sort" onclick={toggleMentionsSort}
			aria-label={`Ordenar menciones ${sortDir === 'desc' ? 'de menor a mayor' : 'de mayor a menor'}`}>
			Menciones: {sortDir === 'desc' ? 'de mayor a menor' : 'de menor a mayor'}
		</button>
		</div>
	</div>

	{#if data.persons.length === 0 && !data.q}
		<div class="person-empty">
			<p class="empty">
				Sin personajes registrados todavía. Los personajes se detectan al enriquecer las
				menciones (protagonistas de cada nota).
			</p>
		</div>
	{:else}
		<div class="directory-result-heading">
			<p role="status" aria-live="polite">
				{filtered.length}
				{filtered.length === 1 ? 'identidad' : 'identidades'} ·
				{filtered.length ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, filtered.length)}
				visibles
			</p>
			<span>{PAGE_SIZE} por página</span>
		</div>
		{#if visible.length}
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
										>{monogram(person.name)}</span
									>
									<div class="directory-person-copy">
										<button class="directory-name" type="button" aria-haspopup="dialog"
											onclick={() => (selected = person)}>{person.name}</button>
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
		{:else}
			{@render directoryEmpty()}
		{/if}
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
		dentro del mismo texto. El directorio carga hasta 200 identidades por búsqueda; el orden ascendente, el seguimiento y sus conteos se aplican a ese conjunto. La ficha consulta el historial en páginas independientes.
	</p>
</details>

{#snippet directoryEmpty()}
	<!-- Mockup directoryResults empty state minus its «Limpiar filtros» button
	     (Julio, L28): the search field and the Todos segment stay visible above,
	     so the button was redundant. -->
	<div class="empty">
		<h3>No hay identidades con estos filtros</h3>
		<p>Prueba otro nombre o cambia el filtro de seguimiento.</p>
	</div>
{/snippet}

<PersonDetailDialog person={selected} onclose={() => (selected = null)} />
