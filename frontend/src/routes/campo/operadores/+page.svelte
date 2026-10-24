<script lang="ts">
	let { data, form } = $props();

	import type { FieldOperatorRecord } from '$lib/api';

	type Operator = FieldOperatorRecord;
	const operators = $derived(data.operators as Operator[]);

	let inviteLink = $state<string | null>(null);

	function statusLabel(operator: Operator): string {
		if (operator.accepted_at) return 'activo';
		if (operator.invited_at) return 'invitado';
		return 'sin invitación';
	}

	function statusClass(operator: Operator): string {
		if (operator.accepted_at) return 'text-success';
		if (operator.invited_at) return 'text-warning';
		return 'text-gray-500';
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
			<a class="underline" href={form.inviteLink} target="_blank">abrir</a>
		{/if}
	</p>
{/if}

<section class="section" aria-labelledby="operators-high">
	<div class="section-heading">
		<h2 id="operators-high">Alta de operador</h2>
	</div>
	<form method="post" action="?/create" class="mt-2 grid gap-2">
		<input
			type="text"
			name="display_name"
			placeholder="Nombre"
			required
			class="min-h-[44px] w-full rounded border px-3"
		/>
		<input
			type="tel"
			name="phone"
			placeholder="Teléfono (ej. 52 222 123 4567)"
			required
			class="min-h-[44px] w-full rounded border px-3"
		/>
		<input
			type="text"
			name="telegram_user_id"
			inputmode="numeric"
			placeholder="Id de Telegram (opcional)"
			class="min-h-[44px] w-full rounded border px-3"
		/>
		<button
			type="submit"
			class="min-h-[44px] rounded-full border border-accent bg-accent px-4 text-sm font-semibold text-accent-on"
		>
			Dar de alta
		</button>
	</form>
</section>

<section class="section" aria-labelledby="operators-list">
	<div class="section-heading">
		<h2 id="operators-list">Operadores ({operators.length})</h2>
	</div>
	{#if operators.length === 0}
		<p class="empty">Sin operadores: dá de alta el primero arriba.</p>
	{:else}
		<ul class="mt-2 grid gap-2">
			{#each operators as operator (operator.id)}
				<li class="rounded border px-3 py-2">
					<div class="flex items-center justify-between gap-3">
						<div class="text-sm">
							<span class="font-semibold">{operator.display_name}</span>
							{#if operator.phone}
								<span class="text-xs text-gray-500"> · {operator.phone}</span>
							{/if}
							{#if operator.telegram_user_id}
								<span class="text-xs text-gray-500"> · tg {operator.telegram_user_id}</span>
							{/if}
							<span class={'text-xs ' + statusClass(operator)}>
								· {statusLabel(operator)}
							</span>
						</div>
						<div class="flex gap-2">
							<form method="post" action="?/invite">
								<input type="hidden" name="id" value={operator.id} />
								<button
									type="submit"
									class="min-h-[44px] rounded-full border px-3 text-sm font-semibold"
								>
									Invitar
								</button>
							</form>
							<form
								method="post"
								action={operator.active ? '?/deactivate' : '?/activate'}
							>
								<input type="hidden" name="id" value={operator.id} />
								<button
									type="submit"
									class="min-h-[44px] rounded-full border px-3 text-sm font-semibold"
								>
									{operator.active ? 'Desactivar' : 'Activar'}
								</button>
							</form>
						</div>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<p class="mt-4 text-xs text-gray-500">
	<a class="underline" href="/campo">← Volver a la cola de reportes</a>
</p>
