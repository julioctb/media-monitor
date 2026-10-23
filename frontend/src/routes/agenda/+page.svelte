<script lang="ts">
	import { enhance } from '$app/forms';

	import type { SubmitFunction } from './$types';
	import { invalidateAll } from '$app/navigation';

	import { formatDateLong } from '$lib/format';
	import type { AgendaItem } from '$lib/api';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const items = $derived(data.items);

	/* Client-side filters: free text over title/location/source plus the
	   «Mostrar» select (mockup agenda-filters). */
	let query = $state('');
	let filter = $state<'all' | 'activity' | 'deadline' | 'undated'>('all');

	const matches = $derived.by(() => {
		const needle = query.trim().toLowerCase();
		return items.filter((item) => {
			if (filter === 'activity' && item.kind !== 'activity') return false;
			if (filter === 'deadline' && item.kind !== 'deadline') return false;
			if (filter === 'undated' && item.event_date) return false;
			if (!needle) return true;
			const haystack = [item.title, item.location, item.source]
				.filter(Boolean)
				.join(' ')
				.toLowerCase();
			return haystack.includes(needle);
		});
	});

	const dated = $derived(items.filter((item) => item.event_date !== null));
	const undated = $derived(items.filter((item) => item.event_date === null));
	const filteredDated = $derived(matches.filter((item) => item.event_date !== null));
	const filteredUndated = $derived(matches.filter((item) => item.event_date === null));

	/* Calendar month cursor: today's month on load; mocked-up views toggle
	   between the grid and the flat list. */
	const now = new Date();
	const cursor = $state({ year: now.getFullYear(), month: now.getMonth() });
	let view = $state<'month' | 'list'>('month');
	const MONTHS_ES = [
		'enero',
		'febrero',
		'marzo',
		'abril',
		'mayo',
		'junio',
		'julio',
		'agosto',
		'septiembre',
		'octubre',
		'noviembre',
		'diciembre'
	];
	const monthLabel = $derived(`${MONTHS_ES[cursor.month]} ${cursor.year}`);

	function shiftMonth(delta: number) {
		const next = new Date(cursor.year, cursor.month + delta, 1);
		cursor.year = next.getFullYear();
		cursor.month = next.getMonth();
		selectedDay = null;
	}

	function goToday() {
		const today = new Date();
		cursor.year = today.getFullYear();
		cursor.month = today.getMonth();
	}

	/** Monday-first grid: leading blanks then one cell per day. */
	const monthCells = $derived.by(() => {
		const days = new Date(cursor.year, cursor.month + 1, 0).getDate();
		const lead = (new Date(cursor.year, cursor.month, 1).getDay() + 6) % 7;
		const cells: (number | null)[] = Array.from({ length: lead }, () => null);
		for (let day = 1; day <= days; day += 1) cells.push(day);
		return cells;
	});

	function dayKey(day: number): string {
		const mm = String(cursor.month + 1).padStart(2, '0');
		const dd = String(day).padStart(2, '0');
		return `${cursor.year}-${mm}-${dd}`;
	}

	const itemsByDay = $derived.by(() => {
		const map = new Map<string, AgendaItem[]>();
		for (const item of filteredDated) {
			const key = item.event_date as string;
			const bucket = map.get(key);
			if (bucket) bucket.push(item);
			else map.set(key, [item]);
		}
		return map;
	});

	let selectedDay = $state<string | null>(null);
	const selectedDayLabel = $derived(
		selectedDay ? formatDateLong(selectedDay) : ''
	);
	const selectedDayItems = $derived(
		selectedDay ? (itemsByDay.get(selectedDay) ?? []) : []
	);

	const KIND_LABEL: Record<string, string> = {
		activity: 'Actividad',
		deadline: 'Plazo de inscripción'
	};

	/** Card secondary line: location · source · notes (mockup .notes). */
	function notesLine(item: AgendaItem): string {
		return [item.location, item.source ? `Fuente: ${item.source}` : null, item.notes]
			.filter(Boolean)
			.join(' · ');
	}

	function dateText(item: AgendaItem): string {
		if (item.event_date) return formatDateLong(item.event_date);
		return item.date_label ?? 'Sin fecha';
	}

	/* Dialogs as conditional panels (jsdom-testable, no native <dialog>). */
	let showForm = $state(false);
	let editTarget = $state<AgendaItem | null>(null);
	let submitting = $state(false);
	let statusMessage = $state('');

	async function handleResult(
		rawResult: unknown,
		update: () => Promise<void>
	) {
		const result = rawResult as { type?: string; data?: { form?: string } };
		if (result.type === 'success') {
			showForm = false;
			editTarget = null;
			statusMessage = result.data?.form === 'date' ? 'Fecha actualizada.' : 'Actividad guardada.';
		}
		await update();
	}

	const handleCreate: SubmitFunction = () => {
		return async ({ result, update }) => {
			submitting = true;
			await handleResult(result, invalidateAll);
			submitting = false;
		};
	};

	const handleEditDate: SubmitFunction = ({ formData }) => {
		formData.set('id', String(editTarget?.id ?? ''));
		return async ({ result, update }) => {
			submitting = true;
			await handleResult(result, invalidateAll);
			submitting = false;
		};
	};

	const todayKey = $derived.by(() => {
		const t = new Date();
		return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, '0')}-${String(
			t.getDate()
		).padStart(2, '0')}`;
	});
</script>

<svelte:head>
	<title>Agenda | Media Monitor</title>
</svelte:head>

<section class="intro" aria-labelledby="agenda-title">
	<div>
		<h1 id="agenda-title" class="page-title">Agenda</h1>
		<p class="lead">Actividades y plazos identificados en la cobertura, reunidos para su seguimiento.</p>
	</div>
	<button class="btn-primary" type="button" onclick={() => (showForm = !showForm)}>
		Añadir actividad
	</button>
</section>

<section class="panel agenda-form-panel" aria-labelledby="form-title" hidden={!showForm}>
	<h2 id="form-title">Nueva actividad</h2>
	<p class="form-help">
		Registra una actividad detectada. Solo el título es obligatorio; puedes completar la fecha
		cuando esté confirmada.
	</p>
	<form
		method="POST"
		action="?/create"
		use:enhance={handleCreate}
	>
		<div class="form-grid">
			<div class="field span-all">
				<label for="activity-title">Título <span aria-hidden="true">*</span></label>
				<input id="activity-title" name="title" required maxlength="240" />
			</div>
			<div class="field span-all">
				<label for="activity-kind">Tipo de registro</label>
				<select id="activity-kind" name="kind">
					<option value="activity">Actividad</option>
					<option value="deadline">Plazo de inscripción</option>
				</select>
			</div>
			<div class="field">
				<label for="activity-date">Fecha de actividad o cierre</label>
				<input type="date" id="activity-date" name="event_date" />
			</div>
			<div class="field">
				<label for="activity-time">Hora</label>
				<input type="time" id="activity-time" name="time" />
			</div>
			<div class="field">
				<label for="activity-location">Lugar</label>
				<input id="activity-location" name="location" />
			</div>
			<div class="field">
				<label for="activity-source">Fuente</label>
				<input id="activity-source" name="source" placeholder="Medio, cuenta o informante" />
			</div>
			<div class="field span-all">
				<label for="activity-url">Enlace a la fuente</label>
				<input id="activity-url" name="url" type="url" placeholder="https://" />
			</div>
			<div class="field span-all">
				<label for="activity-notes">Notas</label>
				<textarea id="activity-notes" name="notes" rows="3"></textarea>
			</div>
		</div>
		{#if form?.form === 'create' && form?.message}
			<p class="agenda-error" role="alert">{form.message}</p>
		{/if}
		<div class="form-actions">
			<button type="button" class="btn-secondary" onclick={() => (showForm = false)}>
				Cancelar
			</button>
			<button type="submit" class="btn-primary" disabled={submitting}>Guardar actividad</button>
		</div>
	</form>
</section>

<section class="panel agenda-toolbar" aria-label="Filtros de agenda">
	<div class="field">
		<label for="agenda-search">Buscar en la agenda</label>
		<input id="agenda-search" type="search" bind:value={query} placeholder="Título, lugar o fuente" />
	</div>
	<div class="field">
		<label for="agenda-filter">Mostrar</label>
		<select id="agenda-filter" bind:value={filter}>
			<option value="all">Todas las actividades</option>
			<option value="activity">Actividades</option>
			<option value="deadline">Plazos de inscripción</option>
			<option value="undated">Fecha por confirmar</option>
		</select>
	</div>
</section>

{#if statusMessage}
	<p class="agenda-status" role="status">{statusMessage}</p>
{/if}

<section aria-labelledby="agenda-list-title">
	<div class="agenda-results-head">
		<h2 id="agenda-list-title">Actividades detectadas</h2>
		<div class="segmented" role="group" aria-label="Vista de agenda">
			<button
				type="button"
				aria-pressed={view === 'month'}
				onclick={() => (view = 'month')}
			>
				Calendario
			</button>
			<button
				type="button"
				aria-pressed={view === 'list'}
				onclick={() => (view = 'list')}
			>
				Lista
			</button>
		</div>
	</div>

	{#if view === 'month'}
		<div class="agenda-month-nav">
			<button type="button" class="btn-secondary" onclick={() => shiftMonth(-1)}>Anterior</button>
			<button type="button" class="btn-secondary" onclick={goToday}>Mes actual</button>
			<button type="button" class="btn-secondary" onclick={() => shiftMonth(1)}>Siguiente</button>
		</div>
		<p class="agenda-month-label">{monthLabel}</p>
		<div class="calendar" role="grid" aria-label="Calendario mensual">
			{#each ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'] as head (head)}
				<span class="calendar-head">{head}</span>
			{/each}
			{#each monthCells as day, i (`cell-${i}`)}
				{#if day === null}
					<span class="calendar-blank"></span>
				{:else}
					{@const key = dayKey(day)}
					{@const dayItems = itemsByDay.get(key) ?? []}
					<button
						type="button"
						class="calendar-day"
						class:today={key === todayKey}
						class:selected={key === selectedDay}
						aria-label={`{day} de ${monthLabel}: {dayItems.length} actividades`}
						onclick={() => (selectedDay = key)}
					>
						<span class="calendar-num">{day}</span>
						{#if dayItems.length > 0}
							<span class="calendar-count">{dayItems.length}</span>
						{/if}
					</button>
				{/if}
			{/each}
		</div>
		{#if selectedDay}
			<section class="day-detail panel" aria-labelledby="day-title">
				<h3 id="day-title" tabindex="-1">{selectedDayLabel}</h3>
				{#if selectedDayItems.length === 0}
					<p class="small-note">Sin actividades para este día.</p>
				{:else}
					<ul class="agenda-list">
						{#each selectedDayItems as item (item.id)}
							<li>
								<article class="activity">
									<div class="date">
										{dateText(item)}
										{#if item.time_label}<span> · {item.time_label}</span>{/if}
										<small>{selectedDay.slice(0, 4)}</small>
									</div>
									<div class="activity-body">
										<span class="badge">{KIND_LABEL[item.kind] ?? item.kind}</span>
										<h4>{item.title}</h4>
										{#if notesLine(item)}<p class="notes">{notesLine(item)}</p>{/if}
									</div>
								</article>
							</li>
						{/each}
					</ul>
				{/if}
			</section>
		{/if}
	{:else}
		<ul class="agenda-list panel">
			{#each filteredDated as item (item.id)}
				<li>
					<article class="activity">
						<div class="date">
							{dateText(item)}
							{#if item.time_label}<span> · {item.time_label}</span>{/if}
							{#if item.event_date}<small>{item.event_date.slice(0, 4)}</small>{/if}
						</div>
						<div class="activity-body">
							<span class="badge">{KIND_LABEL[item.kind] ?? item.kind}</span>
							<h4>{item.title}</h4>
							{#if notesLine(item)}<p class="notes">{notesLine(item)}</p>{/if}
						</div>
					</article>
				</li>
			{/each}
		</ul>
	{/if}

	{#if matches.length === 0}
		<p class="empty mt-4" role="status">No hay actividades para mostrar.</p>
	{/if}

	<section class="panel agenda-pending" aria-labelledby="pending-title">
		<h3 id="pending-title" class="pending-title">Sin fecha completa</h3>
		<p class="pending-note">Solo aparecen aquí los registros que aún no indican día y mes.</p>
		{#if filteredUndated.length === 0}
			<p class="small-note">Nada pendiente de fecha.</p>
		{:else}
			<ul class="agenda-list">
				{#each filteredUndated as item (item.id)}
					<li>
						<article class="activity">
							<div class="date">
								{dateText(item)}
								{#if item.time_label}<span> · {item.time_label}</span>{/if}
							</div>
							<div class="activity-body">
								<span class="badge">{KIND_LABEL[item.kind] ?? item.kind}</span>
								<h4>{item.title}</h4>
								{#if notesLine(item)}<p class="notes">{notesLine(item)}</p>{/if}
								<button
									type="button"
									class="btn-secondary edit-date"
									onclick={() => (editTarget = item)}
								>
									Editar fecha
								</button>
							</div>
						</article>
					</li>
				{/each}
			</ul>
		{/if}
	</section>
</section>

{#if editTarget}
	<section class="panel agenda-form-panel" aria-labelledby="edit-date-title">
		<h2 id="edit-date-title">Editar fecha</h2>
		<p class="form-help">
			Fecha de actividad o cierre para «{editTarget.title}». La hora y el resto de los datos se
			conservan.
		</p>
		<form
			method="POST"
			action="?/editDate"
			use:enhance={handleEditDate}
		>
			<input type="hidden" name="id" value={editTarget.id} />
			<div class="field">
				<label for="edited-date">Fecha de actividad o cierre</label>
				<input id="edited-date" name="event_date" type="date" required />
			</div>
			{#if form?.form === 'date' && form?.message}
				<p class="agenda-error" role="alert">{form.message}</p>
			{/if}
			<div class="form-actions">
				<button type="button" class="btn-secondary" onclick={() => (editTarget = null)}>
					Cancelar
				</button>
				<button type="submit" class="btn-primary" disabled={submitting}>Guardar fecha</button>
			</div>
		</form>
	</section>
{/if}
