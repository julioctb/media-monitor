<script lang="ts">
	import { BTN_PRIMARY_CLS } from '$lib/ui';
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

<header class="persons-intro">
	<h1 class="page-title">Actores</h1>
	<p>
		{data.persons.length}
		protagonistas detectados en la cobertura, con su volumen de menciones.
	</p>
</header>

<section class="directory-panel" aria-labelledby="persons-list-title">
	<div class="directory-header">
		<div>
			<h2 id="persons-list-title">Actores en seguimiento</h2>
			<p role="status" aria-live="polite">
				{data.persons.length}
				{data.persons.length === 1 ? 'persona' : 'personas'} con menciones registradas
			</p>
		</div>
		<form method="get" role="search" class="person-search">
			<label class="search">
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d="M20 20l-5-5 M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14" />
				</svg>
				<span class="sr-only">Buscar actores</span>
				<input
					type="search"
					id="q"
					name="q"
					value={data.q}
					placeholder="Buscar por nombre, cargo o institución"
				/>
			</label>
			<button class={BTN_PRIMARY_CLS} type="submit">Buscar</button>
		</form>
	</div>

	{#if data.persons.length === 0}
		<div class="person-empty">
			<p class="empty">
				Sin actores registrados todavía. Los actores se detectan al enriquecer las menciones
				(protagonistas de cada nota).
			</p>
		</div>
	{:else}
		<div class="directory-table-wrap">
			<table class="directory-table">
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
								<div class="directory-person-cell">
									<span class="directory-monogram" aria-hidden="true"
										>{initials(person.name)}</span
									>
									<div class="directory-person-copy">
										<a class="directory-name" href={`/persons/${person.id}`}>{person.name}</a>
										{#if person.aliases.length > 0}
											<p class="person-aliases">
												También mencionado como: {person.aliases.slice(0, 3).join(', ')}
											</p>
										{/if}
									</div>
								</div>
							</td>
							<td data-label="Cargo">{person.role || '—'}</td>
							<td data-label="Institución">{person.org || '—'}</td>
							<td data-label="Menciones"><strong>{person.mention_count}</strong></td>
							<td data-label="Última vez">
								{#if person.last_seen_at}
									<time datetime={person.last_seen_at}>
										{formatDisplayDateTime(person.last_seen_at)}
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
	{/if}
</section>

<p class="directory-disclaimer">
	Los actores se detectan automáticamente en el enriquecimiento de las notas; la columna «última
	vez» refleja la última mención registrada.
</p>
