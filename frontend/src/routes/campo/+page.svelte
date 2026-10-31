<script lang="ts">
	import { ICON_PATHS } from '$lib/icons';
	import DetailDialog from '$lib/components/DetailDialog.svelte';
	import { enhance } from '$app/forms';
	import type { FieldReportRecord } from '$lib/api';
	import { displayDayKey, formatDisplayDateTime } from '$lib/format';
	import type { SubmitFunction } from './$types';

	let { data, form } = $props();

	type Report = FieldReportRecord;
	/** Fila del directorio: el load añade `last_report_at` derivado de los reportes. */
	type OperatorRow = (typeof data.operators)[number];

	// Estado real del modelo -> pestañas del mockup: review/published/rejected.
	// `draft` (conversación de bot en curso) no entra a la bandeja: sin acción admin.
	const STATUS_TABS = [
		{ key: 'review', label: 'Por revisar' },
		{ key: 'published', label: 'Publicado' },
		{ key: 'rejected', label: 'Descartado' }
	] as const;
	type StatusKey = (typeof STATUS_TABS)[number]['key'];

	// Etiquetas de tono reales (mismas que el mockup app.js `toneLabels`).
	const TONE_LABELS: Record<string, string> = {
		positive: 'Positivo',
		negative: 'Negativo',
		neutral: 'Neutral',
		unclassified: 'Sin clasificar'
	};

	const pending = $derived(data.pending as Report[]);
	const recent = $derived(data.recent as Report[]);
	const operators = $derived(data.operators as OperatorRow[]);
	const reports = $derived([...pending, ...recent]);

	// Sección activa: el mockup abre en «Listado de operadores» (fieldUI.section).
	let section = $state<'operators' | 'reports'>('operators');

	// --- Bandeja de reportes (estado cliente, como field.js `fieldUI`) ---
	let status = $state<StatusKey>('review');
	let query = $state('');
	let dateFrom = $state('');
	let dateTo = $state('');
	let operatorFilter = $state('all');
	let perPage = $state(25);
	let page = $state(1);
	let selectedId = $state<number | null>(null);
	let saving = $state(false);
	let reportError = $state('');

	// --- Listado de operadores ---
	let operatorQuery = $state('');
	let operatorPerPage = $state(5);
	let operatorPage = $state(1);
	let operatorModal = $state<{ mode: 'create' } | { mode: 'edit'; id: number } | null>(null);

	const operatorNames = $derived(new Map(operators.map((operator) => [operator.id, operator.display_name])));

	/** Nombre real si el operador existe en el listado; fallback sin inventar datos. */
	function operatorLabel(id: number | null): string {
		if (id == null) return 'Sin operador';
		return operatorNames.get(id) ?? `Operador #${id}`;
	}

	// Cambiar de sección reinicia filtros (mockup: data-field-section resetea fieldUI).
	function switchSection(next: 'operators' | 'reports') {
		if (next === section) return;
		section = next;
		query = '';
		dateFrom = '';
		dateTo = '';
		operatorFilter = 'all';
		status = 'review';
		page = 1;
		operatorQuery = '';
		operatorPage = 1;
	}

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

	const operatorOptions = $derived.by(() => {
		const ids = new Set<number>();
		for (const report of reports) if (report.operator_id != null) ids.add(report.operator_id);
		return [...ids]
			.map((id) => ({ value: String(id), label: operatorLabel(id) }))
			.sort((a, b) => a.label.localeCompare(b.label, 'es'));
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

	// --- Paginación de operadores (mockup: size 5/10/20) ---
	const filteredOperators = $derived.by(() => {
		const q = operatorQuery.trim().toLocaleLowerCase('es');
		if (!q) return operators;
		return operators.filter((operator) =>
			`${operator.display_name} ${operator.phone ?? ''} ${operator.telegram_user_id ?? ''}`
				.toLocaleLowerCase('es')
				.includes(q)
		);
	});
	const operatorPageCount = $derived(Math.max(1, Math.ceil(filteredOperators.length / operatorPerPage)));
	const operatorCurrentPage = $derived(Math.min(operatorPage, operatorPageCount));
	const operatorSlice = $derived(
		filteredOperators.slice((operatorCurrentPage - 1) * operatorPerPage, operatorCurrentPage * operatorPerPage)
	);

	const editingOperator = $derived.by(() => {
		const modal = operatorModal;
		if (!modal || modal.mode !== 'edit') return null;
		return operators.find((operator) => operator.id === modal.id) ?? null;
	});

	function initials(displayName: string): string {
		const monogram = displayName
			.trim()
			.split(/\s+/)
			.slice(0, 2)
			.map((part) => part.charAt(0))
			.join('');
		return monogram.toLocaleUpperCase('es') || '·';
	}

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

	function resetOperatorPage() {
		operatorPage = 1;
	}

	function openReport(id: number) {
		reportError = '';
		selectedId = id;
	}

	// Un solo <form>, dos intenciones vía formaction (mockup: Publicar / Descartar).
	// Publicar exige resumen; descartar exige motivo (toasts del mockup -> aviso inline).
	const onReportSubmit: SubmitFunction = ({ action, formData }) => {
		const intent = action.search;
		if (intent.includes('approve') && !String(formData.get('content') ?? '').trim()) {
			reportError = 'Completa el resumen antes de publicar.';
			return async () => {};
		}
		if (intent.includes('reject') && !String(formData.get('note') ?? '').trim()) {
			reportError = 'Indica el motivo de descarte.';
			return async () => {};
		}
		reportError = '';
		saving = true;
		return async ({ result, update }) => {
			saving = false;
			if (result.type === 'success') selectedId = null;
			await update();
		};
	};
</script>

<header class="page-header">
	<h1>Campo</h1>
	<p>Operadores y reportes de territorio.</p>
</header>

{#if form?.message}
	<p class="mt-2 text-xs {form.ok ? 'text-success' : 'text-danger'}" role="status">
		{form.message}
		{#if form.ok && 'inviteLink' in form && form.inviteLink}
			<a class="underline" href={form.inviteLink} target="_blank" rel="noopener noreferrer">abrir</a>
		{/if}
	</p>
{/if}

<div class="field-top">
	<div class="tabs" role="group" aria-label="Secciones de Campo">
		<button
			type="button"
			class="tab"
			class:active={section === 'operators'}
			aria-pressed={section === 'operators'}
			onclick={() => switchSection('operators')}
		>
			Listado de operadores
		</button>
		<button
			type="button"
			class="tab"
			class:active={section === 'reports'}
			aria-pressed={section === 'reports'}
			onclick={() => switchSection('reports')}
		>
			Reportes de operadores
		</button>
	</div>
	<span class="chip">Telegram · bot de campo</span>
</div>

<p class="field-notice">
	Origen: bot de Telegram de campo y alta manual. Cada reporte conserva su texto original.
</p>
<p class="field-notice">
	Publicar crea una mención con la fuente «Reporte de campo» y el operador como autor.
</p>

{#if section === 'operators'}
	<section class="panel operators-view" aria-labelledby="operators-heading">
		<div class="field-operator-toolbar">
			<div>
				<h2 id="operators-heading">Listado de operadores</h2>
				<p>{operators.length} operadores registrados</p>
			</div>
			<div class="field-operator-tools">
				<label class="field-search">
					<span>Buscar operador</span>
					<span class="field-search-control">
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
							<path d={ICON_PATHS.search} />
						</svg>
						<input
							type="search"
							placeholder="Nombre, teléfono o ID de Telegram"
							aria-label="Buscar operador"
							bind:value={operatorQuery}
							oninput={resetOperatorPage}
						/>
					</span>
				</label>
				<button type="button" class="button primary" onclick={() => (operatorModal = { mode: 'create' })}>
					Alta de operador
				</button>
			</div>
		</div>

		<div class="field-operator-table-wrap">
			{#if operatorSlice.length === 0}
				<div class="empty">
					<h3>Sin resultados</h3>
					<p>No hay registros en esta selección. Prueba otro filtro o búsqueda.</p>
				</div>
			{:else}
				<table class="field-table">
					<caption class="sr-only">Directorio de operadores de campo</caption>
					<thead>
						<tr>
							<th scope="col">Nombre</th>
							<th scope="col">Teléfono</th>
							<th scope="col">ID de Telegram</th>
							<th scope="col">Estado</th>
							<th scope="col">Último reporte</th>
							<th scope="col">Acciones</th>
						</tr>
					</thead>
					<tbody>
						{#each operatorSlice as operator (operator.id)}
							<tr>
								<td data-label="Nombre">
									<div class="field-operator-cell">
										<span class="field-operator-monogram" aria-hidden="true"
											>{initials(operator.display_name)}</span
										>
										<div><strong>{operator.display_name}</strong></div>
									</div>
								</td>
								<td data-label="Teléfono" class="field-operator-phone">
									{operator.phone ?? 'Sin teléfono'}
								</td>
								<td data-label="ID de Telegram">{operator.telegram_user_id ?? 'Sin vincular'}</td>
								<td data-label="Estado">
									<span
										class="field-operator-status"
										class:is-active={operator.active}
										class:is-inactive={!operator.active}
									>
										{operator.active ? 'Activo' : 'Inactivo'}
									</span>
								</td>
								<td data-label="Último reporte">
									{operator.last_report_at ? formatDisplayDateTime(operator.last_report_at) : 'Sin reportes'}
								</td>
								<td data-label="Acciones">
									<button
										type="button"
										class="button"
										onclick={() => (operatorModal = { mode: 'edit', id: operator.id })}
									>
										Gestionar
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
				{filteredOperators.length === 0 ? 0 : (operatorCurrentPage - 1) * operatorPerPage + 1}–{Math.min(
					operatorCurrentPage * operatorPerPage,
					filteredOperators.length
				)} de {filteredOperators.length} · Página {operatorCurrentPage} de {operatorPageCount}
			</span>
			<label>
				Por página
				<select bind:value={operatorPerPage} onchange={resetOperatorPage} aria-label="Resultados por página">
					{#each [5, 10, 20] as size (size)}
						<option value={size}>{size}</option>
					{/each}
				</select>
			</label>
			<div>
				<button
					type="button"
					class="button"
					disabled={operatorCurrentPage === 1}
					onclick={() => (operatorPage = operatorCurrentPage - 1)}
				>
					Anterior
				</button>
				<button
					type="button"
					class="button"
					disabled={operatorCurrentPage === operatorPageCount}
					onclick={() => (operatorPage = operatorCurrentPage + 1)}
				>
					Siguiente
				</button>
			</div>
		</footer>
	</section>
{:else}
	<section class="panel field-panel reports-view">
		<div class="field-inbox-header">
			<div>
				<h2>Bandeja de reportes</h2>
				<p>{reports.length} reportes registrados · Revisión individual con origen conservado</p>
			</div>
			<label class="field-search">
				<span>Buscar reporte</span>
				<span class="field-search-control">
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
						<path d={ICON_PATHS.search} />
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
				<div class="empty">
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
				<select bind:value={perPage} onchange={resetPage} aria-label="Resultados por página">
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
{/if}

<DetailDialog
	titleId="campo-report-dialog-title"
	title="Reporte de campo"
	open={selected}
	onclose={() => (selectedId = null)}
	variant="field-dialog"
>
	{#if selected}
		<div class="field-report-dialog">
			<div class="field-detail-heading">
				<span class="eyebrow">REPORTE #{selected.id} · {statusLabel(selected.status)}</span>
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

			{#if selected.status === 'review'}
				{#if selected.enrichment}
					<p class="field-notice">
						Sugerencia IA: «{selected.enrichment.suggested_title ?? selected.title ?? ''}» —
						{selected.enrichment.summary ?? 'sin resumen'} (tono:
						{selected.enrichment.tone ? TONE_LABELS[selected.enrichment.tone] ?? selected.enrichment.tone : 'sin clasificar'}).
					</p>
				{/if}
				<form method="POST" class="field-form" use:enhance={onReportSubmit}>
					<label>
						Titular
						<input
							type="text"
							name="title"
							maxlength="140"
							value={selected.title ?? selected.enrichment?.suggested_title ?? ''}
						/>
					</label>
					<label>
						Sentimiento · sugerencia IA
						<input
							type="text"
							value={selected.enrichment?.tone
								? TONE_LABELS[selected.enrichment.tone] ?? selected.enrichment.tone
								: '—'}
							disabled
						/>
					</label>
					<label>
						Resumen para publicar
						<textarea name="content" rows="4" maxlength="5000">{selected.enrichment?.summary ?? selected.content ?? ''}</textarea>
					</label>
					<label>
						Motivo de descarte
						<textarea name="note" rows="2" placeholder="Obligatorio al descartar"></textarea>
					</label>
					<input type="hidden" name="id" value={selected.id} />
					{#if reportError}
						<p class="field-notice text-danger" role="alert">{reportError}</p>
					{/if}
					<div class="field-actions">
						<button class="button primary" type="submit" formaction="?/approve" disabled={saving}>
							Publicar en el Feed
						</button>
						<button class="button" type="submit" formaction="?/reject" disabled={saving}>
							Descartar
						</button>
					</div>
				</form>
				<p class="field-notice">
					Publicar usa el titular y el resumen mostrados. Publicar no verifica los hechos.
				</p>
			{:else if selected.status === 'published'}
				{#if selected.published_at}
					<p class="field-notice">Publicado: {formatDisplayDateTime(selected.published_at)}</p>
				{/if}
				<h3>Resumen publicado</h3>
				<p>{selected.content ?? '(sin contenido)'}</p>
				<p>
					<a class="button" href="/feed?source=field_report">Ver en el Feed</a>
				</p>
			{:else if selected.status === 'rejected'}
				<p class="field-notice">Motivo: {selected.review_note ?? 'Sin motivo'}</p>
			{/if}
		</div>
	{/if}
</DetailDialog>

<DetailDialog
	titleId="campo-operator-dialog-title"
	title={operatorModal?.mode === 'edit' ? 'Gestionar operador' : 'Alta de operador'}
	open={operatorModal}
	onclose={() => (operatorModal = null)}
	variant="field-dialog"
>
	{#if operatorModal}
		<form
			method="POST"
			class="field-form field-operator-form"
			action={operatorModal.mode === 'edit' ? '?/updateOperator' : '?/createOperator'}
		>
			<p class="field-notice">
				El alta no autoriza acceso a Telegram por sí sola: la vinculación se hace aparte con «Invitar al bot».
			</p>
			<label class="field-operator-input">
				<span>Nombre</span>
				<input
					type="text"
					name="display_name"
					maxlength="80"
					autocomplete="name"
					required
					value={editingOperator?.display_name ?? ''}
				/>
			</label>
			<label class="field-operator-input">
				<span>Teléfono</span>
				<input
					type="tel"
					name="phone"
					maxlength="20"
					autocomplete="tel"
					required
					value={editingOperator?.phone ?? ''}
				/>
			</label>
			<div class="field-operator-telegram">
				<span>ID de Telegram</span>
				<div>
					<strong>{editingOperator?.telegram_user_id ?? 'Pendiente de vinculación'}</strong>
					<small>
						{editingOperator?.telegram_user_id
							? 'Asignado por el bot · solo lectura'
							: 'Se asignará mediante el bot'}
					</small>
				</div>
			</div>
			{#if operatorModal.mode === 'edit'}
				<input type="hidden" name="id" value={operatorModal.id} />
			{/if}
			<div class="field-actions">
				<button class="button primary" type="submit">
					{operatorModal.mode === 'edit' ? 'Guardar cambios' : 'Registrar operador'}
				</button>
				{#if editingOperator}
					<button
						class="button"
						type="submit"
						formaction={editingOperator.active ? '?/deactivateOperator' : '?/activateOperator'}
					>
						{editingOperator.active ? 'Desactivar' : 'Activar'}
					</button>
					<button class="button" type="submit" formaction="?/inviteOperator">Invitar al bot</button>
				{/if}
				<button class="button" type="button" onclick={() => (operatorModal = null)}>Cerrar</button>
			</div>
		</form>
	{/if}
</DetailDialog>
