<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';
	import type { PageProps } from './$types';

	let { data, form }: PageProps = $props();

	const BTN_CLS =
		'rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors';
</script>

<svelte:head>
	<title>Palabras clave | Media Monitor</title>
</svelte:head>

<h1 class="text-2xl font-semibold tracking-tight">Palabras clave</h1>
<p class="mt-1 text-sm text-slate-500">Términos monitoreados en noticias y redes.</p>

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

<form method="POST" action="?/create" class="mt-6 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
	<div class="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
		<div>
			<label for="k-text" class="mb-1 block text-xs font-medium text-slate-500">Nueva palabra clave</label>
			<input
				id="k-text"
				name="text"
				value={form?.action === 'create' ? form.text : ''}
				maxlength={500}
				required
				placeholder="Ej. inteligencia artificial"
				class="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200"
			/>
		</div>
		<div>
			<label for="k-lang" class="mb-1 block text-xs font-medium text-slate-500">Idioma</label>
			<select
				id="k-lang"
				name="language"
				class="rounded-lg border border-slate-300 px-3 py-2 text-sm shadow-sm focus:border-slate-500 focus:outline-none"
			>
				<option value="es">Español</option>
				<option value="en">English</option>
			</select>
		</div>
		<button
			type="submit"
			class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
		>
			Agregar
		</button>
	</div>
</form>

{#if data.keywords.length === 0}
	<div class="mt-8 rounded-xl border border-dashed border-slate-300 bg-white p-10 text-center">
		<p class="text-sm font-medium text-slate-700">No hay palabras clave aún.</p>
		<p class="mt-1 text-sm text-slate-500">Agrega la primera con el formulario de arriba.</p>
	</div>
{:else}
	<ul class="mt-6 divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm">
		{#each data.keywords as keyword (keyword.id)}
			<li class="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
				<div class="min-w-0">
					<div class="flex flex-wrap items-center gap-2">
						<span class="text-sm font-medium text-slate-900">{keyword.text}</span>
						<span class="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
							{keyword.language}
						</span>
						{#if !keyword.is_active}
							<span class="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">Inactiva</span>
						{/if}
					</div>
					<p class="mt-0.5 text-xs text-slate-400">
						Creada {formatDisplayDateTime(keyword.created_at)}
					</p>
				</div>

				<div class="flex gap-2">
					<!-- Toggle: PATCH through the form action; the hidden field carries the target state. -->
					<form method="POST" action="?/toggle">
						<input type="hidden" name="id" value={keyword.id} />
						<input type="hidden" name="is_active" value={keyword.is_active ? '0' : '1'} />
						<button type="submit" class={`${BTN_CLS} border-slate-300 text-slate-600 hover:bg-slate-50`}>
							{keyword.is_active ? 'Desactivar' : 'Activar'}
						</button>
					</form>
					<!-- Delete: the action surfaces the 409 detail (mentions referencing it). -->
					<form method="POST" action="?/delete">
						<input type="hidden" name="id" value={keyword.id} />
						<button type="submit" class={`${BTN_CLS} border-red-200 text-red-600 hover:bg-red-50`}>
							Eliminar
						</button>
					</form>
				</div>
			</li>
		{/each}
	</ul>
{/if}
