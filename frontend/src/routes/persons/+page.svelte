<script lang="ts">
	import { BTN_PRIMARY_CLS } from '$lib/ui';
	import { ICON_PATHS } from '$lib/icons';
	import { formatDirectoryDate, formatDisplayTime } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	/** Mockup directoryResults: 25 identities per page. */
	const PAGE_SIZE = 25;

	type SortKey = 'mentions' | 'recent' | 'name';
	let sort = $state<SortKey>('mentions');
	let filtersOpen = $state(false);
	let page = $state(1);
	// A new server payload (new query) restarts the visible window.
	$effect(() => {
		data.q;
		page = 1;
	});

	// Client-side view over the loaded set (presentation only; the server
	// payload stays untouched). Ties break by name, like the mockup.
	const sorted = $derived.by(() => {
		const list = [...data.persons];
		const nameOrder = (a: (typeof list)[number], b: (typeof list)[number]) =>
			a.name.localeCompare(b.name, 'es');
		if (sort === 'mentions')
			list.sort(
				(a, b) => b.mention_count - a.mention_count || nameOrder(a, b)
			);
		else if (sort === 'recent')
			list.sort(
				(a, b) =>
					(b.last_seen_at ?? '').localeCompare(a.last_seen_at ?? '') ||
					nameOrder(a, b)
			);
		else list.sort(nameOrder);
		return list;
	});

	const pages = $derived(Math.max(1, Math.ceil(sorted.length / PAGE_SIZE)));
	const currentPage = $derived(Math.min(page, pages));
	const offset = $derived((currentPage - 1) * PAGE_SIZE);
	const visible = $derived(sorted.slice(offset, offset + PAGE_SIZE));

	function onSortChange(event: Event) {
		sort = (event.target as HTMLSelectElement).value as SortKey;
		page = 1;
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
				{data.persons.length === 1 ? 'identidad detectada' : 'identidades detectadas'}
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
		<button
			type="button"
			class="directory-filter-toggle"
			aria-controls="directory-advanced-filters"
			aria-expanded={filtersOpen}
			onclick={() => (filtersOpen = !filtersOpen)}
		>
			Filtrar
		</button>
		<div class="directory-filters {filtersOpen ? 'is-open' : ''}" id="directory-advanced-filters">
			<label>
				<span>Ordenar por</span>
				<select value={sort} onchange={onSortChange}>
					<option value="recent">Más recientes</option>
					<option value="mentions">Más mencionados</option>
					<option value="name">Nombre A–Z</option>
				</select>
			</label>
		</div>
	</div>

	{#if data.persons.length === 0}
		{#if data.q}
			<div class="empty">
				<h3>No hay identidades con estos filtros</h3>
				<p>Prueba con otro nombre o variante.</p>
				<a class="button" href="/persons">Ver todos</a>
			</div>
		{:else}
			<div class="person-empty">
				<p class="empty">
					Sin personajes registrados todavía. Los personajes se detectan al enriquecer las
					menciones (protagonistas de cada nota).
				</p>
			</div>
		{/if}
	{:else}
		<div class="directory-result-heading">
			<p role="status" aria-live="polite">
				{sorted.length}
				{sorted.length === 1 ? 'identidad' : 'identidades'} ·
				{sorted.length ? offset + 1 : 0}–{Math.min(offset + PAGE_SIZE, sorted.length)} visibles
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
						<th scope="col">Menciones</th>
						<th scope="col">Fuentes</th>
						<th scope="col">Última aparición</th>
					</tr>
				</thead>
				<tbody>
					{#each visible as person (person.id)}
						<tr>
							<td data-label="Nombre">
								<div class="directory-person-cell">
									<span class="directory-monogram" aria-hidden="true"
										>{initials(person.name)}</span
									>
									<div class="directory-person-copy">
										<a class="directory-name" href={`/persons/${person.id}`}>{person.name}</a>
									</div>
								</div>
							</td>
							<td data-label="Tipo">Persona</td>
							<td data-label="Menciones"><strong>{person.mention_count}</strong></td>
							<td data-label="Fuentes">
								<span class="muted">—</span>
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
