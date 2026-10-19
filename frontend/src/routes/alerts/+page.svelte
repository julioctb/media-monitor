<script lang="ts">
	import type { PageProps } from './$types';

	import { INPUT_CLS } from '$lib/ui';

	let { data, form }: PageProps = $props();


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

<h1 class="page-title">Alertas</h1>
<p class="lead">
	Recibe menciones por email según la frecuencia configurada.
</p>

{#if form}
	<div
		role={form.ok ? 'status' : 'alert'}
		class={`mt-4 rounded-lg px-4 py-3 text-sm ring-1 ring-inset ${
			form.ok
				? 'bg-success/10 text-success ring-success/30'
				: 'bg-danger/10 text-danger ring-danger/30'
		}`}
	>
		{form.message}
	</div>
{/if}

<form method="POST" action="?/save" class="filter-panel max-w-xl">
	<div class="space-y-4">
		<div>
			<label for="a-digest" class="mb-1 block text-xs font-medium text-ink-2">
				Frecuencia del resumen
			</label>
			<select id="a-digest" name="digest" class={INPUT_CLS}>
				{#each digestOptions as option (option.value)}
					<option value={option.value} selected={current.digest === option.value}>{option.label}</option>
				{/each}
			</select>
		</div>

		<div>
			<label for="a-email" class="mb-1 block text-xs font-medium text-ink-2">
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

		<label class="flex items-center gap-2 text-sm text-ink-2">
			<input
				type="checkbox"
				name="is_active"
				value="1"
				checked={current.is_active}
				class="size-4 rounded border-line accent-accent"
			/>
			Activar alertas
		</label>

		<div class="rounded-xl border border-line-soft bg-surface-warm p-3">
			<p class="text-xs font-medium text-muted">Alerta de viraje de sentimiento (búsquedas guardadas)</p>
			<label class="mt-2 flex items-center gap-2 text-sm text-ink-2">
				<input
					type="checkbox"
					name="sentiment_shift_enabled"
					value="1"
					checked={current.sentiment_shift_enabled}
					class="size-4 rounded border-line accent-accent"
				/>
				Cuando el balance positivo/negativo gira más allá del umbral
			</label>
			<label for="a-shift-threshold" class="mt-2 block text-xs font-medium text-muted">
				Umbral en puntos porcentuales
			</label>
			<input
				id="a-shift-threshold"
				name="sentiment_shift_threshold"
				type="number"
				min="1"
				max="100"
				step="0.5"
				value={current.sentiment_shift_threshold}
				class={`mt-1 w-32 ${INPUT_CLS}`}
			/>
		</div>
	</div>

	<button
		type="submit"
		class="mt-5 inline-flex min-h-[44px] items-center justify-center rounded-full border border-accent bg-accent px-[22px] text-sm font-semibold text-accent-on transition-colors hover:border-accent-hover hover:bg-accent-hover active:border-accent-active active:bg-accent-active disabled:opacity-60"
	>
		Guardar configuración
	</button>
</form>
