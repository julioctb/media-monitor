<script lang="ts">
	import { BTN_PRIMARY_CLS, INPUT_CLS } from '$lib/ui';
	import { formatDisplayDateTime } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();


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
	<title>Actores | Media Monitor</title>
</svelte:head>

<header class="flex flex-col gap-3">
	<div>
		<h1 class="page-title">Actores</h1>
		<p class="lead">
			{data.persons.length}
			protagonistas detectados en la cobertura, con su volumen de menciones.
		</p>
	</div>
</header>

<section class="filter-panel" aria-labelledby="persons-filter-title">
	<h2 class="panel-title" id="persons-filter-title">Filtrar actores</h2>
	<form method="get" class="filter-form mt-3">
		<div class="min-w-0 flex-1">
			<label class="mb-1.5 block text-xs font-semibold text-ink-2" for="q">Buscar actor</label>
			<input
				class={`${INPUT_CLS} min-w-0`}
				id="q"
				type="search"
				name="q"
				value={data.q}
				placeholder="Nombre, cargo o institución"
			/>
		</div>
		<button class={BTN_PRIMARY_CLS} type="submit">Buscar</button>
	</form>
</section>

<section class="panel" aria-labelledby="persons-list-title">
	<div class="panel-head">
		<h2 class="panel-title" id="persons-list-title">Actores en seguimiento</h2>
		<p class="panel-note" role="status" aria-live="polite">
			{data.persons.length}
			{data.persons.length === 1 ? 'persona' : 'personas'} con menciones registradas
		</p>
	</div>
	{#if data.persons.length === 0}
		<p class="empty mt-4">
			Sin actores registrados todavía. Los actores se detectan al enriquecer las menciones
			(protagonistas de cada nota).
		</p>
	{:else}
		<div class="table-wrap mt-4">
			<table class="data-table">
				<thead>
					<tr>
						<th scope="col">Nombre</th>
						<th scope="col">Cargo</th>
						<th scope="col">Institución</th>
						<th scope="col">Menciones</th>
						<th scope="col">Última vez</th>
					</tr>
				</thead>
				<tbody>
					{#each data.persons as person (person.id)}
						<tr>
							<td data-label="Nombre">
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
							<td data-label="Institución">{person.org || '—'}</td>
							<td data-label="Menciones"><span class="count">{person.mention_count}</span></td>
							<td data-label="Última vez">
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
	{/if}
</section>

<p class="footnote">
	Los actores se detectan automáticamente en el enriquecimiento de las notas; la columna «última
	vez» refleja la última mención registrada.
</p>
