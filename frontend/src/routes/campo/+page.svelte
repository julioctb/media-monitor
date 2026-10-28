<script lang="ts">
	let { data, form } = $props();

	import { tick } from 'svelte';
	import { enhance } from '$app/forms';
	import type { FieldReportRecord } from '$lib/api';
	import { displayDayKey, formatDisplayDateTime } from '$lib/format';
	import type { SubmitFunction } from './$types';

	type Report = FieldReportRecord;

	// Estado real del modelo -> pestañas del mockup: review/published/rejected.
	// `draft` (conversación de bot en curso) no entra a la bandeja: sin acción admin.
	const STATUS_TABS = [
		{ key: 'review', label: 'Por revisar' },
		{ key: 'published', label: 'Publicado' },
		{ key: 'rejected', label: 'Descartado' }
	] as const;
	type StatusKey = (typeof STATUS_TABS)[number]['key'];

	const pending = $derived(data.pending as Report[]);
	const recent = $derived(data.recent as Report[]);
	const reports = $derived([...pending, ...recent]);

	let status = $state<StatusKey>('review');
	let query = $state('');
	let dateFrom = $state('');
	let dateTo = $state('');
	let operatorFilter = $state('all');
	let perPage = $state(25);
	let page = $state(1);
	let selectedId = $state<number | null>(null);
	let saving = $state(false);
	let dialogEl: HTMLDialogElement | null = null;

	const countByStatus = $derived.by(() => {
		const counts: Record<StatusKey, number> = {
			review: pending.length,
			published: 0,
			rejected: 0
		};
		for (const report of recent) {
			if (report.status === 'published') counts.published += 1;
			else if (report.status === 'rejected') counts.rejected += 1;
		}
		return counts;
	});

	function operatorLabel(operatorId: number | null): string {
		return operatorId == null ? 'Sin operador' : `Operador #${operatorId}`;
	}

	const operatorOptions = $derived.by(() => {
		const ids = new Set<number>();
		for (const report of reports) if (report.operator_id != null) ids.add(report.operator_id);
		return [...ids].sort((a, b) => a - b).map((id) => ({ value: String(id), label: operatorLabel(id) }));
	});

	const dateRangeError = $derived(dateFrom !== '' && dateTo !== '' && dateFrom > dateTo);

	const filtered = $derived.by(() => {
		const q = query.trim().toLocaleLowerCase('es');
		return reports
			.filter((report) => report.status === status)
			.filter((report) => {
				const day = displayDayKey(report.created_at);
				return (!dateFrom || (day !== '' && day >= dateFrom)) && (!dateTo || (day !== '' && day <= dateTo));
			})
			.filter((report) => operatorFilter === 'all' || String(report.operator_id ?? '') === operatorFilter)
			.filter(
				(report) =>
					query.trim() === '' ||
					`${report.title ?? ''} ${operatorLabel(report.operator_id)} ${report.place ?? ''}`
						.toLocaleLowerCase('es')
						.includes(q)
			)
			.sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''));
	});

	const pageCount = $derived(Math.max(1, Math.ceil(filtered.length / perPage)));
	const currentPage = $derived(Math.min(page, pageCount));
	const pageSlice = $derived(filtered.slice((currentPage - 1) * perPage, currentPage * perPage));

	const selected = $derived(
		selectedId == null ? null : (reports.find((report) => report.id === selectedId) ?? null)
	);

	function receptionParts(report: Report): { day: string; time: string } {
		if (!report.created_at) return { day: 'sin fecha', time: '' };
		const [day, time = ''] = formatDisplayDateTime(report.created_at).split(' ');
		return { day, time };
	}

	function rowSummary(report: Report): string {
		return report.enrichment?.summary ?? report.content ?? '';
	}

	function statusLabel(value: Report['status']): string {
		return STATUS_TABS.find((tab) => tab.key === value)?.label ?? value;
	}

	function resetPage() {
		page = 1;
	}

	async function openReport(id: number) {
		selectedId = id;
		await tick();
		// jsdom no implementa showModal; los navegadores reales sí.
		if (typeof dialogEl?.showModal === 'function') dialogEl.showModal();
	}

	function closeReport() {
		dialogEl?.close();
	}

	// Un solo <form>, tres acciones vía formaction: update (guardar), approve, reject.
	const onSubmit: SubmitFunction = () => {
		saving = true;
		return async ({ result, update }) => {
			saving = false;
			if (result.type === 'success') closeReport();
			await update();
		};
	};
</script>

<header class="page-header">
	<h1>Reportes de campo</h1>
	<p class="page-sub">
		Bandeja de entrada del canal humano: lo que reporta la gente en territorio, antes de entrar al
		feed.
	</p>
</header>

{#if form?.message}
	<p class="mt-2 text-xs {form.ok ? 'text-success' : 'text-danger'}" role="status">
		{form.message}
	</p>
{/if}

<div class="field-top">
	<div class="tabs">
		<a class="tab" href="/campo/operadores">Listado de operadores</a>
		<button class="tab active" type="button" aria-pressed="true">Reportes de operadores</button>
	</div>
	<span class="chip">Telegram · bot de campo</span>
</div>

<p class="field-notice">
	Origen: bot de Telegram de campo y alta manual. Cada reporte conserva su texto original.
</p>
<p class="field-notice">
	Publicar crea una mención con la fuente «Reporte de campo» y el operador como autor.
</p>

<section class="panel field-panel reports-view">
	<div class="field-inbox-header">
		<div>
			<h2>Bandeja de reportes</h2>
			<p>{reports.length} reportes cargados · Revisión con origen conservado</p>
		</div>
		<label class="field-search">
			<span>Buscar reporte</span>
			<span class="field-search-control">
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d="M20 20l-5-5 M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14" />
				</svg>
				<input
					type="search"
					placeholder="Título, operador o lugar"
					aria-label="Buscar reporte"
					bind:value={query}
					oninput={resetPage}
				/>
			</span>
		</label>
	</div>

	<div class="field-inbox-toolbar">
		<div class="field-inbox-status" role="group" aria-label="Estado del reporte">
			{#each STATUS_TABS as tab (tab.key)}
				<button
					type="button"
					class={status === tab.key ? 'active' : ''}
					aria-pressed={status === tab.key}
					onclick={() => {
						status = tab.key;
						resetPage();
					}}
				>
					{tab.label}<span>{countByStatus[tab.key]}</span>
				</button>
			{/each}
		</div>

		<fieldset class="field-date-range">
			<legend>Periodo</legend>
			<div class="field-date-range-inputs">
				<label>
					Desde
					<input type="date" bind:value={dateFrom} max={dateTo || undefined} oninput={resetPage} />
				</label>
				<label>
					Hasta
					<input type="date" bind:value={dateTo} min={dateFrom || undefined} oninput={resetPage} />
				</label>
			</div>
			{#if dateRangeError}
				<p class="field-date-error" role="alert">«Desde» no puede ser posterior a «Hasta».</p>
			{/if}
		</fieldset>

		<label>
			Operador
			<select bind:value={operatorFilter} onchange={resetPage}>
				<option value="all">Todos los operadores</option>
				{#each operatorOptions as option (option.value)}
					<option value={option.value}>{option.label}</option>
				{/each}
			</select>
		</label>
	</div>

	<div class="field-inbox-table-wrap">
		{#if pageSlice.length === 0}
			<div class="feed-empty">
				<h3>Sin resultados</h3>
				<p>No hay registros en esta selección. Prueba otro filtro o búsqueda.</p>
			</div>
		{:else}
			<table class="field-inbox-table">
				<caption class="sr-only">
					Reportes de campo filtrados por estado, periodo y operador
				</caption>
				<thead>
					<tr>
						<th scope="col">Recepción</th>
						<th scope="col">Reporte</th>
						<th scope="col">Operador</th>
						<th scope="col">Lugar</th>
						<th scope="col">Estado</th>
						<th scope="col"><span class="sr-only">Acción</span></th>
					</tr>
				</thead>
				<tbody>
					{#each pageSlice as report (report.id)}
						{@const reception = receptionParts(report)}
						<tr>
							<td data-label="Recepción">
								<time datetime={report.created_at ?? undefined}>
									{reception.day}<span>{reception.time}</span>
								</time>
							</td>
							<td data-label="Reporte">
								<button type="button" class="field-inbox-title" onclick={() => openReport(report.id)}>
									{report.title ?? '(sin título)'}
								</button>
								<span class="field-inbox-summary">{rowSummary(report)}</span>
							</td>
							<td data-label="Operador">{operatorLabel(report.operator_id)}</td>
							<td data-label="Lugar">{report.place ?? '—'}</td>
							<td data-label="Estado">
								<span class="field-inbox-state {report.status}">{statusLabel(report.status)}</span>
							</td>
							<td data-label="Acción">
								<button type="button" class="button" onclick={() => openReport(report.id)}>
									{report.status === 'review' ? 'Revisar' : 'Abrir'}
								</button>
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		{/if}
	</div>

	<footer class="field-pagination">
		<span role="status">
			{filtered.length === 0 ? 0 : (currentPage - 1) * perPage + 1}–{Math.min(
				currentPage * perPage,
				filtered.length
			)} de {filtered.length} · Página {currentPage} de {pageCount}
		</span>
		<label>
			Por página
			<select
				bind:value={perPage}
				onchange={resetPage}
				aria-label="Resultados por página"
			>
				{#each [25, 50, 100] as size (size)}
					<option value={size}>{size}</option>
				{/each}
			</select>
		</label>
		<div>
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
				disabled={currentPage === pageCount}
				onclick={() => (page = currentPage + 1)}
			>
				Siguiente
			</button>
		</div>
	</footer>
</section>

<dialog class="field-dialog" aria-labelledby="field-dialog-title" bind:this={dialogEl} onclose={() => (selectedId = null)}>
	{#if selected}
		<div class="dialog-head">
			<strong id="field-dialog-title">Reporte de campo</strong>
			<button class="icon-button" type="button" onclick={closeReport} aria-label="Cerrar detalle">
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12 M6 18 18 6" /></svg>
			</button>
		</div>
		<div class="dialog-body">
			<div class="field-report-dialog">
				<div class="field-detail-heading">
					<span class="eyebrow">Reporte #{selected.id} · {statusLabel(selected.status)}</span>
					<h2>{selected.title ?? '(sin título)'}</h2>
				</div>

				<dl class="field-metadata">
					<div>
						<dt>Operador</dt>
						<dd>{operatorLabel(selected.operator_id)}</dd>
					</div>
					<div>
						<dt>Lugar</dt>
						<dd>{selected.place ?? '—'}</dd>
					</div>
					<div>
						<dt>Recepción</dt>
						<dd>{selected.created_at ? formatDisplayDateTime(selected.created_at) : 'sin fecha'}</dd>
					</div>
					{#if selected.published_at}
						<div>
							<dt>Publicación</dt>
							<dd>{formatDisplayDateTime(selected.published_at)}</dd>
						</div>
					{/if}
				</dl>

				<h3>Reporte original</h3>
				<blockquote>{selected.content ?? '(sin contenido)'}</blockquote>

				{#if selected.enrichment}
					<p class="field-notice">
						Sugerencia IA{#if selected.enrichment.duplicate} · posible duplicado{/if}:
						“{selected.enrichment.suggested_title ?? selected.title ?? ''}”{#if selected.enrichment.summary}
							— {selected.enrichment.summary}
						{/if}{#if selected.enrichment.tone}
							(tono: {selected.enrichment.tone})
						{/if}
					</p>
				{/if}

				{#if selected.status === 'rejected' && selected.review_note}
					<p class="field-notice">Motivo del descarte: {selected.review_note}</p>
				{/if}

				{#if selected.status === 'review'}
					<form method="POST" class="field-form" use:enhance={onSubmit}>
						<label>
							Titular
							<input type="text" name="title" value={selected.title ?? ''} />
						</label>
						<label>
							Lugar
							<input type="text" name="place" value={selected.place ?? ''} />
						</label>
						<label>
							Contenido a publicar
							<textarea name="content" rows="4">{selected.content ?? ''}</textarea>
						</label>
						<label>
							Motivo del descarte
							<textarea name="note" rows="2" placeholder="Opcional"></textarea>
						</label>
						<input type="hidden" name="id" value={selected.id} />
						<div class="field-actions">
							<button class="button primary" type="submit" formaction="?/approve" disabled={saving}>
								Publicar en el Feed
							</button>
							<button class="button" type="submit" formaction="?/reject" disabled={saving}>
								Descartar
							</button>
							<button class="button subtle" type="submit" disabled={saving}>Guardar cambios</button>
						</div>
					</form>
					<p class="field-notice">
						«Publicar» y «Descartar» usan la versión guardada; guarda los cambios antes de aplicarlos.
					</p>
				{/if}

				{#if selected.status === 'published'}
					<p>
						<a class="button" href="/feed?source=field_report">Ver en el feed</a>
					</p>
				{/if}
			</div>
		</div>
	{/if}
</dialog>
