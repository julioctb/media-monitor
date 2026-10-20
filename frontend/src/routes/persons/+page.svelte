<script lang="ts">
	import { page } from '$app/state';

	import { BTN_PRIMARY_CLS, COMPACT_CLS, CONTROL_CLS, INPUT_CLS } from '$lib/ui';
	import { formatDisplayDateTime } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();


	let filterForm: HTMLFormElement | undefined = $state();
	function submitFilters() {
		filterForm?.requestSubmit();
	}

	function hrefWith(param: Record<string, string>): string {
		const params = new URLSearchParams(page.url.searchParams);
		for (const [key, value] of Object.entries(param)) {
			if (value) params.set(key, value);
			else params.delete(key);
		}
		const qs = params.toString();
		return `${page.url.pathname}${qs ? `?${qs}` : ''}`;
	}

	const view = $derived(data.view === 'cards' ? 'cards' : 'table');

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
	<title>Personas | Media Monitor</title>
</svelte:head>

<header class="flex flex-wrap items-end justify-between gap-4">
	<div>
		<h1 class="page-title">Personas</h1>
		<p class="lead">
			{data.persons.length}
			protagonistas detectados en la cobertura, con su volumen de menciones.
		</p>
	</div>
	<nav class="segmented" aria-label="Vista">
		<a href={hrefWith({ view: 'cards' })} aria-current={view === 'cards' ? 'page' : undefined}>
			Tarjetas
		</a>
		<a href={hrefWith({ view: 'table' })} aria-current={view === 'table' ? 'page' : undefined}>
			Tabla
		</a>
	</nav>
</header>

<section class="filter-panel" aria-labelledby="persons-filter-title">
	<h2 class="panel-title" id="persons-filter-title">Filtrar personas</h2>
	<form bind:this={filterForm} method="get" class="filter-form mt-3">
		<div class="min-w-0 flex-1">
			<label class="mb-1.5 block text-xs font-semibold text-ink-2" for="q">Buscar persona</label>
			<input
				class={`${INPUT_CLS} min-w-0`}
				id="q"
				type="search"
				name="q"
				value={data.q}
				placeholder="Buscar por nombre"
			/>
		</div>
		<div>
			<label class="mb-1.5 block text-xs font-semibold text-ink-2" for="sort">Orden</label>
			<select id="sort" name="sort" class={COMPACT_CLS} onchange={submitFilters}>
				<option value="mentions" selected={data.sort === 'mentions'}>Más mencionadas</option>
				<option value="recent" selected={data.sort === 'recent'}>Actividad reciente</option>
			</select>
		</div>
		<button class={BTN_PRIMARY_CLS} type="submit">Buscar</button>
	</form>
</section>

<section class="panel" aria-labelledby="persons-list-title">
	<div class="panel-head">
		<h2 class="panel-title" id="persons-list-title">Personas en seguimiento</h2>
		<p class="panel-note" role="status" aria-live="polite">
			{data.persons.length}
			{data.persons.length === 1 ? 'persona' : 'personas'} con menciones registradas
		</p>
	</div>
	{#if data.persons.length === 0}
		<p class="empty mt-4">
			Sin personas registradas todavía. Las personas se detectan al enriquecer las menciones
			(protagonistas de cada nota).
		</p>
	{:else if view === 'table'}
		<div class="table-wrap mt-4">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">Persona</th>
						<th scope="col">Cargo</th>
						<th scope="col">Medio</th>
						<th scope="col">Menciones</th>
						<th scope="col">Última vez vista</th>
					</tr>
				</thead>
				<tbody>
					{#each data.persons as person (person.id)}
						<tr>
							<td data-label="Persona">
								<div class="flex items-center gap-3 font-semibold">
									<span class="monogram" aria-hidden="true">{initials(person.name)}</span>
									<a
										class="underline decoration-line underline-offset-[3px] hover:decoration-ink"
										href={`/persons/${person.id}`}>{person.name}</a
									>
									{#if person.aliases.length > 0}
										<span class="text-xs font-normal text-meta">
											también: {person.aliases.slice(0, 2).join(', ')}
										</span>
									{/if}
								</div>
							</td>
							<td data-label="Cargo">{person.role || '—'}</td>
							<td data-label="Medio">{person.org || '—'}</td>
							<td data-label="Menciones"><span class="count">{person.mention_count}</span></td>
							<td data-label="Última vez vista">
								{#if person.last_seen_at}
									{formatDisplayDateTime(person.last_seen_at)}
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
		<ul class="mt-4 grid gap-3 md:grid-cols-2" aria-label="Personas">
			{#each data.persons as person (person.id)}
				<li>
					<a
						href={`/persons/${person.id}`}
						class="block rounded-2xl border border-line-soft bg-white p-5 transition-colors hover:border-line"
					>
						<div class="flex items-baseline justify-between gap-2">
							<h3 class="text-sm font-semibold text-ink">{person.name}</h3>
							<span class="shrink-0 text-xs tabular-nums text-muted">
								{person.mention_count}
								{person.mention_count === 1 ? 'mención' : 'menciones'}
							</span>
						</div>
						{#if person.role || person.org}
							<p class="mt-1 text-xs text-muted">
								{[person.role, person.org].filter(Boolean).join(' · ')}
							</p>
						{/if}
						{#if person.aliases.length > 0}
							<p class="mt-1 text-xs text-meta">
								También: {person.aliases.slice(0, 3).join(', ')}
							</p>
						{/if}
						<p class="mt-2 text-xs text-meta">
							Ultima vez vista {formatDisplayDateTime(person.last_seen_at)}
						</p>
					</a>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<p class="footnote">
	Los actores se detectan automáticamente en el enriquecimiento de las notas; la columna «última
	vez vista» refleja la última mención registrada.
</p>
