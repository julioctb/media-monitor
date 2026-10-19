<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';
	import { BTN_PRIMARY_CLS, COMPACT_CLS, INPUT_CLS } from '$lib/ui';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const BTN_CLS =
		'rounded-full border px-3 py-1.5 text-xs font-medium transition-colors';
</script>

<svelte:head>
	<title>Palabras clave | Media Monitor</title>
</svelte:head>

<h1 class="page-title">Palabras clave</h1>
<p class="lead">Términos monitoreados en noticias y redes.</p>

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

<form method="POST" action="?/create" class="filter-panel">
	<div class="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
		<div>
			<label for="k-text" class="mb-1 block text-xs font-medium text-ink-2">Nueva palabra clave</label>
			<input
				id="k-text"
				name="text"
				value={form?.action === 'create' ? form.text : ''}
				maxlength={500}
				required
				placeholder="Ej. inteligencia artificial"
				class={INPUT_CLS}
			/>
		</div>
		<div>
			<label for="k-lang" class="mb-1 block text-xs font-medium text-ink-2">Idioma</label>
			<select id="k-lang" name="language" class={COMPACT_CLS}>
				<option value="es">Español</option>
				<option value="en">English</option>
			</select>
		</div>
		<button type="submit" class={BTN_PRIMARY_CLS}>Agregar</button>
	</div>
</form>

{#if data.keywords.length === 0}
	<div class="empty mt-6">
		<p class="font-medium text-ink">No hay palabras clave aún.</p>
		<p class="mt-1">Agrega la primera con el formulario de arriba.</p>
	</div>
{:else}
	<ul class="mt-6 divide-y divide-line-soft rounded-2xl border border-line-soft bg-white">
		{#each data.keywords as keyword (keyword.id)}
			<li class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
				<div class="min-w-0">
					<div class="flex flex-wrap items-center gap-2">
						<span class="text-sm font-medium text-ink">{keyword.text}</span>
						<span class="rounded-full bg-surface px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-muted">
							{keyword.language}
						</span>
						{#if !keyword.is_active}
							<span class="rounded-full border border-line bg-surface px-2 py-0.5 text-xs text-muted">Inactiva</span>
						{/if}
					</div>
					<p class="mt-0.5 text-xs text-meta">
						Creada {formatDisplayDateTime(keyword.created_at)}
					</p>
				</div>

				<div class="flex gap-2">
					<!-- Toggle: PATCH through the form action; the hidden field carries the target state. -->
					<form method="POST" action="?/toggle">
						<input type="hidden" name="id" value={keyword.id} />
						<input type="hidden" name="is_active" value={keyword.is_active ? '0' : '1'} />
						<button type="submit" class={`${BTN_CLS} border-line text-ink-2 hover:bg-surface-warm`}>
							{keyword.is_active ? 'Desactivar' : 'Activar'}
						</button>
					</form>
					<!-- Delete: the action surfaces the 409 detail (mentions referencing it). -->
					<form method="POST" action="?/delete">
						<input type="hidden" name="id" value={keyword.id} />
						<button type="submit" class={`${BTN_CLS} border-danger/40 text-danger hover:bg-danger/10`}>
							Eliminar
						</button>
					</form>
				</div>
			</li>
		{/each}
	</ul>
{/if}
