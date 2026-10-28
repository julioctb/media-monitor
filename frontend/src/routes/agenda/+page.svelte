<script lang="ts">
	import { enhance } from '$app/forms';
	import { invalidateAll } from '$app/navigation';

	import type { SubmitFunction } from './$types';
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

	const filteredDated = $derived(matches.filter((item) => item.event_date !== null));
	const filteredUndated = $derived(matches.filter((item) => item.event_date === null));

	/* Calendar month cursor: today's month on load; the segmented switch only
	   toggles the grid, the list stays the filtered set (mockup
	   calendar-view-switch). */
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
		selectedDay = null;
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

	/* Month view status (mockup .calendar-toolbar count line). */
	const monthItemCount = $derived.by(() => {
		const prefix = `${cursor.year}-${String(cursor.month + 1).padStart(2, '0')}`;
		return filteredDated.filter((item) => item.event_date?.startsWith(prefix)).length;
	});
	const monthCountLabel = $derived(
		`${monthItemCount} ${monthItemCount === 1 ? 'actividad con fecha' : 'actividades con fecha'} en el mes`
	);

	/* The shared list: pending cards under the month grid, everything filtered
	   in list view. */
	const listItems = $derived(view === 'month' ? filteredUndated : matches);

	let selectedDay = $state<string | null>(null);
	const selectedDayLabel = $derived(
		/* Noon anchor: date-only strings parse as UTC and the Mexico City
		   formatter would show the previous evening's date. */
		selectedDay ? formatDateLong(`${selectedDay}T12:00:00Z`) : ''
	);
	const selectedDayItems = $derived(
		selectedDay ? (itemsByDay.get(selectedDay) ?? []) : []
	);

	/** schedule-row date box (mockup .date-box): month abbr + day via pure
	    string math on the ISO date, so no timezone can shift the day. */
	const MONTHS_ABBR = [
		'ene',
		'feb',
		'mar',
		'abr',
		'may',
		'jun',
		'jul',
		'ago',
		'sep',
		'oct',
		'nov',
		'dic'
	];
	function monthAbbrOf(eventDate: string): string {
		const match = /^(\d{4})-(\d{2})/.exec(eventDate);
		return match ? MONTHS_ABBR[Number(match[2]) - 1] : '';
	}
	function dayNumberOf(eventDate: string): string {
		const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(eventDate);
		return match ? String(Number(match[3])) : eventDate;
	}

	const KIND_LABEL: Record<string, string> = {
		activity: 'Actividad',
		deadline: 'Plazo de inscripción'
	};

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
			statusMessage =
				result.data?.form === 'date'
					? 'Fecha actualizada.'
					: result.data?.form === 'delete'
						? 'Actividad eliminada.'
						: 'Actividad guardada.';
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

	const handleDelete: SubmitFunction = () => {
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

{#snippet activityCard(item: AgendaItem)}
	<article class="activity">
		<div class="date-box">
			{#if item.event_date}
				<span>{monthAbbrOf(item.event_date)}</span>
				<strong>{dayNumberOf(item.event_date)}</strong>
			{:else}
				<span>{item.date_label ?? 'Por confirmar'}</span>
			{/if}
			{#if item.time_label}<span>{item.time_label}</span>{/if}
		</div>
		<div class="activity-body">
			<span class="tone-badge">{KIND_LABEL[item.kind] ?? item.kind}</span>
			<h3>{item.title}</h3>
			<dl class="details">
				<div>
					<dt>Lugar</dt>
					<dd>{item.location || 'Por confirmar'}</dd>
				</div>
				<div>
					<dt>Fuente</dt>
					<dd>{item.source || 'No indicada'}</dd>
				</div>
				{#if item.url}
					<div>
						<dt>Enlace</dt>
						<dd>
							<a
								href={item.url}
								target="_blank"
								rel="noopener noreferrer"
								aria-label={`Ver fuente de ${item.title} (abre otra pestaña)`}>Ver fuente</a
							>
						</dd>
					</div>
				{/if}
			</dl>
			{#if item.notes}<p class="notes">{item.notes}</p>{/if}
		</div>
		<div class="activity-actions">
			<button type="button" class="button" onclick={() => (editTarget = item)}>
				Editar fecha
			</button>
			<form class="delete-form" method="POST" action="?/remove" use:enhance={handleDelete}>
				<input type="hidden" name="id" value={item.id} />
				<button type="submit" class="button subtle" disabled={submitting}>Eliminar</button>
			</form>
		</div>
	</article>
{/snippet}

<header class="agenda-intro">
	<div>
		<h1 class="page-title">Agenda</h1>
		<p>Las fechas del monitoreo, convertidas en próximos pasos.</p>
	</div>
	<button class="button primary" type="button" onclick={() => (showForm = !showForm)}>
		Añadir actividad
	</button>
</header>

<section class="panel agenda-form-panel" aria-labelledby="form-title" hidden={!showForm}>
	<h2 id="form-title">Nueva actividad</h2>
	<p class="form-intro">
		Registra una actividad detectada. Solo el título es obligatorio; puedes completar la fecha
		cuando esté confirmada.
	</p>
	<form method="POST" action="?/create" use:enhance={handleCreate}>
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
			<div class="field span-all">
				<label for="activity-location">Lugar</label>
				<input id="activity-location" name="location" />
			</div>
			<div class="field span-all">
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
			<button type="button" class="button" onclick={() => (showForm = false)}>Cancelar</button>
			<button type="submit" class="button primary" disabled={submitting}>
				Guardar actividad
			</button>
		</div>
	</form>
</section>

<section class="agenda-toolbar" aria-label="Filtros de agenda">
	<div class="field field-search">
		<label for="agenda-search">Buscar en la agenda</label>
		<input id="agenda-search" type="search" bind:value={query} placeholder="Título, lugar o fuente" />
	</div>
	<div class="field field-filter">
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

<section class="panel calendar-panel" aria-label="Actividades de la agenda">
	<div class="calendar-toolbar">
		<div class="calendar-month-field">
			<h2 id="calendar-month" aria-live="polite">{monthLabel}</h2>
			<span class="calendar-count">{monthCountLabel}</span>
		</div>
		<div class="calendar-controls">
			<div class="calendar-view-switch" role="group" aria-label="Vista de la agenda">
				<button
					type="button"
					class="button"
					class:primary={view === 'month'}
					aria-pressed={view === 'month'}
					onclick={() => (view = 'month')}
				>
					Mes
				</button>
				<button
					type="button"
					class="button"
					class:primary={view === 'list'}
					aria-pressed={view === 'list'}
					onclick={() => (view = 'list')}
				>
					Lista
				</button>
			</div>
			<div class="calendar-nav">
				<button type="button" class="button" aria-label="Mes anterior" onclick={() => shiftMonth(-1)}>
					Anterior
				</button>
				<button type="button" class="button" onclick={goToday}>Mes actual</button>
				<button type="button" class="button" aria-label="Mes siguiente" onclick={() => shiftMonth(1)}>
					Siguiente
				</button>
			</div>
		</div>
	</div>

	{#if view === 'month'}
		<div class="calendar-month">
			<p class="calendar-hint">Selecciona un día para consultar sus actividades y fuentes.</p>
			<div class="calendar-week" aria-hidden="true">
				{#each ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'] as head (head)}
					<span>{head}</span>
				{/each}
			</div>
			<div class="calendar-grid" role="group" aria-labelledby="calendar-month">
				{#each monthCells as day, i (`cell-${i}`)}
					{#if day === null}
						<div class="calendar-blank" aria-hidden="true"></div>
					{:else}
						{@const key = dayKey(day)}
						{@const dayItems = itemsByDay.get(key) ?? []}
						{#if dayItems.length > 0}
							<button
								type="button"
								class="calendar-day has-events"
								class:today={key === todayKey}
								class:selected={selectedDay === key}
								aria-pressed={selectedDay === key}
								aria-label={`${day} de ${monthLabel}: ${dayItems.map((it) => it.title).join('; ')}`}
								onclick={() => (selectedDay = key)}
							>
								<span class="calendar-number">{day}</span>
								<span class="calendar-event-count">
									{dayItems.length}
									<span class="calendar-count-label">
										{dayItems.length === 1 ? 'actividad' : 'actividades'}
									</span>
								</span>
								<span class="calendar-preview od-clamp-2" aria-hidden="true">
									{dayItems[0].title}
								</span>
							</button>
						{:else}
							<div class="calendar-day" class:today={key === todayKey}>
								<span class="calendar-number">{day}</span>
							</div>
						{/if}
					{/if}
				{/each}
			</div>
		</div>
		{#if selectedDay}
			<div class="calendar-list-heading">
				<h3 id="day-title">Actividades del {selectedDayLabel}</h3>
				<button type="button" class="text-link" onclick={() => (selectedDay = null)}>
					Ver todo el mes
				</button>
			</div>
			{#if selectedDayItems.length > 0}
				<ul class="agenda-list">
					{#each selectedDayItems as item (item.id)}
						<li>{@render activityCard(item)}</li>
					{/each}
				</ul>
			{:else if filteredUndated.length === 0}
				<p class="agenda-day-empty">
					Sin actividades este día; selecciona otra fecha o revisa la lista completa.
				</p>
			{/if}
		{/if}
		{#if filteredUndated.length > 0}
			<h3 class="pending-title">Sin fecha completa ({filteredUndated.length})</h3>
		{/if}
	{/if}
	<ul class="agenda-list">
		{#each listItems as item (item.id)}
			<li>{@render activityCard(item)}</li>
		{/each}
	</ul>
	{#if view === 'list' && matches.length === 0}
		<div class="agenda-empty">
			<h3>No hay actividades para mostrar</h3>
			<p>Prueba otra búsqueda o cambia el filtro.</p>
		</div>
	{/if}
</section>

<details class="agenda-about">
	<summary>Acerca de esta agenda</summary>
	<p>
		Las actividades y los plazos se detectan automáticamente en el
		<a href="/">resumen del día</a>; también puedes registrarlos manualmente con «Añadir
		actividad».
	</p>
	<p>
		Si una fuente indica día y mes pero no el año, se asigna el año siguiente al detector. La fecha
		se completa o corrige con «Editar fecha».
	</p>
</details>

{#if editTarget}
	<section class="panel agenda-form-panel" aria-labelledby="edit-date-title">
		<h2 id="edit-date-title">Editar fecha</h2>
		<p class="edit-context">
			Fecha de actividad o cierre para «{editTarget.title}». La hora y el resto de los datos se
			conservan.
		</p>
		<form method="POST" action="?/editDate" use:enhance={handleEditDate}>
			<div class="field">
				<label for="edited-date">Fecha de actividad o cierre</label>
				<input id="edited-date" name="event_date" type="date" required value={editTarget.event_date ?? ''} />
			</div>
			{#if form?.form === 'date' && form?.message}
				<p class="agenda-error" role="alert">{form.message}</p>
			{/if}
			<div class="form-actions">
				<button type="button" class="button" onclick={() => (editTarget = null)}>Cancelar</button>
				<button type="submit" class="button primary" disabled={submitting}>Guardar fecha</button>
			</div>
		</form>
	</section>
{/if}
