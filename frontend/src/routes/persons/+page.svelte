<script lang="ts">
	import { page } from '$app/state';
	import { formatDisplayDateTime } from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const INPUT_CLS =
		'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';

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
</div>

<form bind:this={filterForm} method="get" class="mt-6 flex flex-wrap items-center gap-2">
	<input
		type="search"
		name="q"
		value={data.q}
		placeholder="Buscar por nombre"
		aria-label="Buscar persona"
		class={`${INPUT_CLS} min-w-0 flex-1 basis-64`}
	/>
	<select name="sort" aria-label="Orden" class={INPUT_CLS} onchange={submitFilters}>
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
