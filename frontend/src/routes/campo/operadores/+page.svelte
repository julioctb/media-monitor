<script lang="ts">
	import { ICON_PATHS } from '$lib/icons';
	let { data, form } = $props();

	import type { FieldOperatorRecord } from '$lib/api';
	import { formatDisplayDateTime } from '$lib/format';

	/** Fila del directorio: el load añade `last_report_at` derivado de los reportes. */
	type OperatorRow = FieldOperatorRecord & { last_report_at: string | null };

	const operators = $derived(data.operators as OperatorRow[]);

	// svelte-ignore state_referenced_locally — snapshot inicial: el alta solo
	// abre por defecto cuando aún no existe ningún operador.
	let formOpen = $state((data.operators as OperatorRow[]).length === 0);
	let query = $state('');
	let manageId = $state<number | null>(null);

	const filtered = $derived.by(() => {
		const q = query.trim().toLocaleLowerCase('es');
		if (!q) return operators;
		return operators.filter((operator) =>
			`${operator.display_name} ${operator.phone ?? ''} ${operator.telegram_user_id ?? ''}`
				.toLocaleLowerCase('es')
				.includes(q)
		);
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

	// Detalle de alta: la celda de estado es Activo/Inactivo (mockup); la
	// distinción invitación/aceptación vive en el panel de gestión para no
	// perder el estado real del modelo.
	function lifecycle(operator: OperatorRow): string {
		if (operator.accepted_at) return `Aceptó el ${formatDisplayDateTime(operator.accepted_at)}`;
		if (operator.invited_at) return `Invitado el ${formatDisplayDateTime(operator.invited_at)}`;
		return 'Sin invitación al bot';
	}
</script>

<header class="page-header">
	<h1>Operadores de campo</h1>
	<p class="page-sub">
		La lista blanca del bot: solo teléfonos cargados aquí pueden reportar. La
		invitación es un link; el alta se confirma cuando la persona comparte su
		teléfono al entrar.
	</p>
</header>

{#if form?.message}
	<p class="mt-2 text-xs {form.ok ? 'text-success' : 'text-danger'}" role="status">
		{form.message}
		{#if form.ok && form.inviteLink}
			<a class="underline" href={form.inviteLink} target="_blank" rel="noopener noreferrer">abrir</a>
		{/if}
	</p>
{/if}

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
						bind:value={query}
					/>
				</span>
			</label>
			<button
				type="button"
				class="button primary"
				aria-expanded={formOpen}
				aria-controls="operator-create-form"
				onclick={() => (formOpen = !formOpen)}
			>
				Alta de operador
			</button>
		</div>
	</div>

	<form
		id="operator-create-form"
		class="field-form field-operator-form"
		hidden={!formOpen}
		method="post"
		action="?/create"
	>
		<label>
			Nombre
			<input type="text" name="display_name" placeholder="Nombre y apellido" required />
		</label>
		<label>
			Teléfono
			<input type="tel" name="phone" placeholder="Ej. 52 222 123 4567" required />
		</label>
		<label>
			ID de Telegram (opcional)
			<input
				type="text"
				name="telegram_user_id"
				inputmode="numeric"
				placeholder="Se asigna vía bot si se omite"
			/>
		</label>
		<div class="field-actions">
			<button type="submit" class="button primary">Registrar operador</button>
		</div>
	</form>

	<div class="field-operator-table-wrap">
		{#if operators.length === 0}
			<div class="feed-empty">
				<h3>Sin operadores</h3>
				<p>Dá de alta al primero con el botón «Alta de operador».</p>
			</div>
		{:else if filtered.length === 0}
			<div class="feed-empty">
				<h3>Sin resultados</h3>
				<p>Ningún operador coincide con la búsqueda.</p>
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
					{#each filtered as operator (operator.id)}
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
									aria-expanded={manageId === operator.id}
									aria-controls={`operator-manage-${operator.id}`}
									onclick={() => (manageId = manageId === operator.id ? null : operator.id)}
								>
									Gestionar
								</button>
							</td>
						</tr>
						{#if manageId === operator.id}
							<tr class="field-operator-manage-row" id={`operator-manage-${operator.id}`}>
								<td colspan={6}>
									<div class="field-operator-manage">
										<p class="field-operator-manage-note">{lifecycle(operator)}</p>
										<div class="field-actions">
											<form method="post" action={operator.active ? '?/deactivate' : '?/activate'}>
												<input type="hidden" name="id" value={operator.id} />
												<button type="submit" class="button">
													{operator.active ? 'Desactivar' : 'Activar'}
												</button>
											</form>
											<form method="post" action="?/invite">
												<input type="hidden" name="id" value={operator.id} />
												<button type="submit" class="button">Invitar al bot</button>
											</form>
										</div>
									</div>
								</td>
							</tr>
						{/if}
					{/each}
				</tbody>
			</table>
		{/if}
	</div>
</section>

<p class="field-return">
	<a class="text-link" href="/campo">← Volver a la cola de reportes</a>
</p>
