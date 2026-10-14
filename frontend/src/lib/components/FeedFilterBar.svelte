<script lang="ts">
	import type { Keyword } from '$lib/api';
	import { sourceLabel } from '$lib/format';

	interface FeedFilters {
		source: string;
		sentiment: string;
		keyword_id: string;
		political: string;
		since: string;
		until: string;
		q: string;
		limit: number;
	}

	interface Props {
		sources: string[];
		keywords: Keyword[];
		filters: FeedFilters;
		/** Bare feed path: the Limpiar link resets every param. */
		resetHref: string;
	}

	let { sources, keywords, filters, resetHref }: Props = $props();

	// Compact pills: same box height as a chip, native picker inside.
	const PILL_CLS =
		'rounded-full border border-slate-300 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 shadow-sm hover:border-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';
	const FIELD_CLS =
		'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';
	const LABEL_CLS = 'mb-1 block text-xs font-medium text-slate-500';

	const sentimentOptions: Array<{ value: string; label: string }> = [
		{ value: '', label: 'Todos' },
		{ value: 'positive', label: 'Positivo' },
		{ value: 'negative', label: 'Negativo' },
		{ value: 'neutral', label: 'Neutro' },
		{ value: 'none', label: 'Sin clasificar' }
	];
	const limitOptions = [25, 50, 100, 200];

	let formEl: HTMLFormElement | undefined = $state();

	function autoSubmit() {
		// GET submit → same URL-param contract as before, full page keeps SSR state.
		formEl?.requestSubmit();
	}

	// Advanced = everything folded into the disclosure except the pagination
	// limit (a size knob) and the search box (promoted to the main row).
	const advancedCount = $derived.by(() => {
		let count = 0;
		if (filters.keyword_id !== '') count += 1;
		if (filters.political === '1') count += 1;
		if (filters.since !== '') count += 1;
		if (filters.until !== '') count += 1;
		return count;
	});
</script>

<!-- Filters: plain GET form, works without JavaScript. The pills auto-submit
	when JS is available; the hidden-in-details Aplicar button covers no-JS. -->
<form bind:this={formEl} method="get" class="mt-6 flex flex-wrap items-center gap-2 rounded-xl border border-slate-200 bg-white px-3 py-2 shadow-sm">
	<div>
		<label class="sr-only" for="f-source">Fuente</label>
		<select id="f-source" name="source" class={PILL_CLS} onchange={autoSubmit}>
			<option value="">Todas las fuentes</option>
			{#each sources as source (source)}
				<option value={source} selected={filters.source === source}>{sourceLabel(source)}</option>
			{/each}
		</select>
	</div>

	<div>
		<label class="sr-only" for="f-sentiment">Sentimiento</label>
		<select id="f-sentiment" name="sentiment" class={PILL_CLS} onchange={autoSubmit}>
			{#each sentimentOptions as option (option.value)}
				<option value={option.value} selected={filters.sentiment === option.value}>
					{option.label}
				</option>
			{/each}
		</select>
	</div>

	<!-- Búsqueda: primary filter, always visible; Enter submits via the
		Aplicar button (first submit in tree order, works with details closed). -->
	<div class="min-w-0 flex-1 basis-40">
		<label class="sr-only" for="f-q">Búsqueda</label>
		<input
			type="search"
			id="f-q"
			name="q"
			value={filters.q}
			placeholder="Buscar en título o contenido"
			class={`${FIELD_CLS} min-w-0`}
		/>
	</div>

	<details class="min-w-0">
		<summary
			class="flex cursor-pointer list-none items-center gap-1.5 rounded-full px-2 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
		>
			Más filtros
			{#if advancedCount > 0}
				<span
					class="flex size-4.5 items-center justify-center rounded-full bg-slate-900 text-[10px] font-semibold text-white"
					aria-label="{advancedCount} filtros avanzados activos"
				>
					{advancedCount}
				</span>
			{/if}
		</summary>

		<div class="mt-3 grid gap-4 rounded-lg bg-slate-50 p-3 sm:grid-cols-2 lg:grid-cols-4">
			<div>
				<label class={LABEL_CLS} for="f-keyword">Palabra clave</label>
				<select id="f-keyword" name="keyword_id" class={FIELD_CLS}>
					<option value="">Todas</option>
					{#each keywords as keyword (keyword.id)}
						<option value={String(keyword.id)} selected={filters.keyword_id === String(keyword.id)}>
							{keyword.text}{keyword.is_active ? '' : ' · inactiva'}
						</option>
					{/each}
				</select>
			</div>

			<div>
				<span class={LABEL_CLS}>Clasificación</span>
				<label class="flex items-center gap-2 text-sm text-slate-700">
					<input
						type="checkbox"
						name="political"
						value="1"
						checked={filters.political === '1'}
						class="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-200"
					/>
					Solo políticas
				</label>
			</div>

			<div>
				<span class={LABEL_CLS}>Fecha publicación (UTC)</span>
				<div class="flex flex-wrap items-center gap-2">
					<input
						type="date"
						name="since"
						value={filters.since}
						aria-label="Desde"
						class={`${FIELD_CLS} min-w-0 flex-1 basis-28`}
					/>
					<span class="text-xs text-slate-400">a</span>
					<input
						type="date"
						name="until"
						value={filters.until}
						aria-label="Hasta"
						class={`${FIELD_CLS} min-w-0 flex-1 basis-28`}
					/>
				</div>
			</div>

			<div>
				<label class={LABEL_CLS} for="f-limit">Por página</label>
				<select id="f-limit" name="limit" class={FIELD_CLS}>
					{#each limitOptions as option (option)}
						<option value={String(option)} selected={filters.limit === option}>{option}</option>
					{/each}
				</select>
			</div>

			<div class="flex items-end">
				<button
					type="submit"
					class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
				>
					Aplicar
				</button>
			</div>
		</div>
	</details>

	<a
		href={resetHref}
		class="rounded px-1 py-1 text-xs text-slate-400 underline underline-offset-2 hover:text-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300"
	>
		Limpiar
	</a>
</form>
