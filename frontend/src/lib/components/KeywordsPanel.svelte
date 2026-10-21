<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';
	import { INPUT_CLS } from '$lib/ui';
	import type { Keyword } from '$lib/api';

	interface FormResult {
		action?: string;
		ok?: boolean;
		message?: string;
		text?: string;
	}

	interface Props {
		keywords: Keyword[];
		/** Action result from the host page, used to restore the term input. */
		form?: FormResult | null;
	}

	let { keywords, form = null }: Props = $props();

	const btn =
		'inline-flex min-h-[44px] items-center justify-center rounded-full border px-3 text-xs font-semibold transition-colors disabled:opacity-60';
</script>

<form method="POST" action="?/create" class="keyword-form">
	<div>
		<label class="field-label" for="k-text">Nueva palabra clave</label>
		<input
			id="k-text"
			name="text"
			value={form?.action === 'create' ? form.text ?? '' : ''}
			maxlength={500}
			required
			placeholder="Ej. BUAP"
			aria-label="Palabra clave"
			class={INPUT_CLS}
		/>
	</div>
	<div>
		<label class="field-label" for="k-lang">Idioma</label>
		<select id="k-lang" name="language" class={INPUT_CLS}>
			<option value="es">Español</option>
			<option value="en">English</option>
		</select>
	</div>
	<button type="submit" class={`${btn} border-accent bg-accent text-accent-on hover:bg-accent-hover`}>
		Añadir
	</button>
</form>

<div class="table-wrap">
	{#if keywords.length === 0}
		<p class="keywords-empty">No hay palabras clave configuradas.</p>
	{:else}
		<table class="keywords">
			<thead>
				<tr>
					<th scope="col">Palabra clave</th>
					<th scope="col">Idioma</th>
					<th scope="col">Creación</th>
					<th scope="col">Estado</th>
					<th scope="col">Acciones</th>
				</tr>
			</thead>
			<tbody>
				{#each keywords as keyword (keyword.id)}
					<tr>
						<td data-label="Palabra clave">{keyword.text}</td>
						<td data-label="Idioma">{keyword.language}</td>
						<td data-label="Creación">{formatDisplayDateTime(keyword.created_at)}</td>
						<td data-label="Estado">
							<span class="status-chip {keyword.is_active ? 'on' : 'off'}">
								{keyword.is_active ? 'Activa' : 'Inactiva'}
							</span>
						</td>
						<td data-label="Acciones">
							<div class="row-actions">
								<form method="POST" action="?/toggle">
									<input type="hidden" name="id" value={keyword.id} />
									<input type="hidden" name="is_active" value={keyword.is_active ? '0' : '1'} />
									<button type="submit" class={`${btn} btn-small border-line text-ink-2 hover:bg-surface-warm`}>
										{keyword.is_active ? 'Desactivar' : 'Activar'}
									</button>
								</form>
								<form method="POST" action="?/delete">
									<input type="hidden" name="id" value={keyword.id} />
									<button
										type="submit"
										class={`${btn} btn-small btn-delete border-line text-ink-2 hover:bg-surface-warm`}
									>
										Eliminar
									</button>
								</form>
							</div>
						</td>
					</tr>
				{/each}
			</tbody>
		</table>
	{/if}
</div>
