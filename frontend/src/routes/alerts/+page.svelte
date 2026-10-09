<script lang="ts">
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const INPUT_CLS =
		'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';

	const digestOptions = [
		{ value: 'instant', label: 'Instante (un email por mención)' },
		{ value: 'daily', label: 'Diario' },
		{ value: 'weekly', label: 'Semanal' }
	] as const;

	// Keep the user's input on validation errors; show saved state otherwise.
	const current = $derived(!form || form.ok ? data.settings : form.values);
</script>

<svelte:head>
	<title>Alertas | Media Monitor</title>
</svelte:head>

<h1 class="text-2xl font-semibold tracking-tight">Alertas</h1>
<p class="mt-1 text-sm text-slate-500">
	Recibe menciones por email según la frecuencia configurada.
</p>

{#if form}
	<div
		role={form.ok ? 'status' : 'alert'}
		class={`mt-4 rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${
			form.ok
				? 'bg-green-50 text-green-800 ring-green-600/20'
				: 'bg-red-50 text-red-800 ring-red-600/20'
		}`}
	>
		{form.message}
	</div>
{/if}

<form method="POST" action="?/save" class="mt-6 max-w-xl rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
	<div class="space-y-4">
		<div>
			<label for="a-digest" class="mb-1 block text-xs font-medium text-slate-500">
				Frecuencia del resumen
			</label>
			<select id="a-digest" name="digest" class={INPUT_CLS}>
				{#each digestOptions as option (option.value)}
					<option value={option.value} selected={current.digest === option.value}>{option.label}</option>
				{/each}
			</select>
		</div>

		<div>
			<label for="a-email" class="mb-1 block text-xs font-medium text-slate-500">
				Email de destino
			</label>
			<input
				id="a-email"
				name="recipient_email"
				type="email"
				required
				value={current.recipient_email ?? ''}
				placeholder="alertas@ejemplo.com"
				class={INPUT_CLS}
			/>
		</div>

		<label class="flex items-center gap-2 text-sm text-slate-700">
			<input
				type="checkbox"
				name="is_active"
				value="1"
				checked={current.is_active}
				class="size-4 rounded border-slate-300 text-slate-900 focus:ring-slate-300"
			/>
			Activar alertas
		</label>
	</div>

	<button
		type="submit"
		class="mt-5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
	>
		Guardar configuración
	</button>
</form>
