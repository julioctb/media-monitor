<script lang="ts">
	import { page } from '$app/state';

	import { CONTROL_CLS, INPUT_CLS } from '$lib/ui';
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
</script>

<svelte:head>
	<title>Personas | Media Monitor</title>
</svelte:head>

<div class="flex flex-wrap items-end justify-between gap-3">
	<div>
		<h1 class="text-2xl font-semibold tracking-tight">Personas</h1>
		<p class="mt-1 text-sm text-slate-500">
			{data.persons.length}
			protagonistas detectados en la cobertura, con su volumen de menciones.
		</p>
	</div>
	<div class="flex rounded-lg border border-slate-200 bg-white p-0.5 shadow-sm">
		<a
			href={hrefWith({ view: 'cards' })}
			aria-current={view === 'cards' ? 'page' : undefined}
			class={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
				view === 'cards'
					? 'bg-slate-900 text-white'
					: 'text-slate-600 hover:text-slate-900'
			}`}
		>
			Tarjetas
		</a>
		<a
			href={hrefWith({ view: 'table' })}
			aria-current={view === 'table' ? 'page' : undefined}
			class={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
				view === 'table'
					? 'bg-slate-900 text-white'
					: 'text-slate-600 hover:text-slate-900'
			}`}
		>
			Tabla
		</a>
	</div>
</div>

<form bind:this={filterForm} method="get" class="mt-6 flex flex-wrap items-center gap-2 md:flex-nowrap">
	<input
		type="search"
		name="q"
		value={data.q}
		placeholder="Buscar por nombre"
		aria-label="Buscar persona"
		class={`${INPUT_CLS} min-w-0 flex-1`}
	/>
	<select
		name="sort"
		aria-label="Orden"
		class={`${CONTROL_CLS} w-auto px-3 py-2`}
		onchange={submitFilters}
	>
		<option value="mentions" selected={data.sort === 'mentions'}>Más mencionadas</option>
		<option value="recent" selected={data.sort === 'recent'}>Actividad reciente</option>
	</select>
	<button
		type="submit"
		class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
	>
		Buscar
	</button>
</form>

{#if data.persons.length === 0}
	<div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
		<p class="text-sm font-medium text-slate-700">Sin personas registradas todavía.</p>
		<p class="mt-1 text-sm text-slate-500">
			Las personas se detectan al enriquecer las menciones (protagonistas de cada nota).
		</p>
	</div>
{:else if view === 'table'}
	<div class="mt-6 overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
		<table class="w-full text-left text-sm">
			<thead>
				<tr class="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
					<th scope="col" class="px-4 py-3 font-medium">Persona</th>
					<th scope="col" class="px-4 py-3 font-medium">Cargo</th>
					<th scope="col" class="px-4 py-3 font-medium">Medio</th>
					<th scope="col" class="px-4 py-3 text-right font-medium">Menciones</th>
					<th scope="col" class="px-4 py-3 font-medium">Última vez vista</th>
				</tr>
			</thead>
			<tbody>
				{#each data.persons as person (person.id)}
					<tr class="border-b border-slate-100 last:border-0 hover:bg-slate-50">
						<td class="px-4 py-3">
							<a
								href={`/persons/${person.id}`}
								class="font-medium text-slate-900 underline-offset-2 hover:underline"
							>
								{person.name}
							</a>
							{#if person.aliases.length > 0}
								<span class="ml-2 text-xs text-slate-400">
									también: {person.aliases.slice(0, 2).join(', ')}
								</span>
							{/if}
						</td>
						<td class="px-4 py-3 text-slate-600">
							{person.role || '—'}
						</td>
						<td class="px-4 py-3 text-slate-600">
							{person.org || '—'}
						</td>
						<td class="px-4 py-3 text-right tabular-nums text-slate-700">
							{person.mention_count}
						</td>
						<td class="px-4 py-3 text-slate-500">
							{formatDisplayDateTime(person.last_seen_at)}
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<ul class="mt-6 grid gap-3 md:grid-cols-2" aria-label="Personas">
		{#each data.persons as person (person.id)}
			<li>
				<a
					href={`/persons/${person.id}`}
					class="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm transition-colors hover:border-slate-300"
				>
					<div class="flex items-baseline justify-between gap-2">
						<h2 class="text-sm font-semibold text-slate-900">{person.name}</h2>
						<span class="shrink-0 text-xs tabular-nums text-slate-500">
							{person.mention_count}
							{person.mention_count === 1 ? 'mención' : 'menciones'}
						</span>
					</div>
					{#if person.role || person.org}
						<p class="mt-1 text-xs text-slate-500">
							{[person.role, person.org].filter(Boolean).join(' · ')}
						</p>
					{/if}
					{#if person.aliases.length > 0}
						<p class="mt-1 text-xs text-slate-400">
							También: {person.aliases.slice(0, 3).join(', ')}
						</p>
					{/if}
					<p class="mt-2 text-xs text-slate-400">
						Ultima vez vista {formatDisplayDateTime(person.last_seen_at)}
					</p>
				</a>
			</li>
		{/each}
	</ul>
{/if}
