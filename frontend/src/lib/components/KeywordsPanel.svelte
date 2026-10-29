<script lang="ts">
	import { enhance } from '$app/forms';
	import { formatDisplayDateTime } from '$lib/format';
	import { INPUT_CLS } from '$lib/ui';
	import type { Keyword, KeywordLanguage } from '$lib/api';

	const LANGUAGE_LABEL: Record<KeywordLanguage, string> = {
		es: 'Español',
		en: 'Inglés',
		other: 'Otro'
	};

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

	/** Gates the create submit while its action is in flight. */
	let creating = $state(false);
</script>

<!-- Mockup configKeywords: soft add-row (label wrapping its control) feeding
     the framed keyword directory below. Row actions use the shared directory
     button system (.button / .text-link), not the global pills. -->
<form
	method="POST"
	action="?/create"
	class="config-form-row"
	use:enhance={() => {
		creating = true;
		return async ({ update }) => {
			// Default reset on success; on failure the term input recalls its
			// value from `form`.
			await update();
			creating = false;
		};
	}}
>
	<label for="k-text">
		Palabra clave
		<input
			id="k-text"
			name="text"
			value={form?.action === 'create' ? form.text ?? '' : ''}
			maxlength={120}
			required
			placeholder="Añadir término"
			class={INPUT_CLS}
		/>
	</label>
	<label for="k-lang">
		Idioma
		<select id="k-lang" name="language" class={INPUT_CLS}>
			<option value="es">Español</option>
			<option value="en">Inglés</option>
			<option value="other">Otro</option>
		</select>
	</label>
	<button type="submit" class="button" data-config-keyword-add disabled={creating}>
		Añadir
	</button>
</form>

<!-- tabindex makes the scrollable frame keyboard-reachable (mockup pattern). -->
<!-- svelte-ignore a11y_no_noninteractive_tabindex -->
<div class="config-rss-table-frame" role="region" aria-label="Listado de palabras clave" tabindex="0">
	<table class="config-rss-table config-keyword-table">
		<thead>
			<tr>
				<th scope="col">Palabra clave</th>
				<th scope="col">Idioma</th>
				<th scope="col">Añadida</th>
				<th scope="col">Estado</th>
				<th scope="col">Acciones</th>
			</tr>
		</thead>
		<tbody>
			{#each keywords as keyword (keyword.id)}
				<tr>
					<th scope="row">{keyword.text}</th>
					<td>{LANGUAGE_LABEL[keyword.language] ?? keyword.language}</td>
					<td>{formatDisplayDateTime(keyword.created_at)}</td>
					<!-- Estado es texto plano en el directorio del mockup, sin chip. -->
					<td>{keyword.is_active ? 'Activa' : 'Inactiva'}</td>
					<td>
						<div class="config-keyword-actions">
							<form method="POST" action="?/toggle" use:enhance>
								<input type="hidden" name="id" value={keyword.id} />
								<input type="hidden" name="is_active" value={keyword.is_active ? '0' : '1'} />
								<button type="submit" class="button">
									{keyword.is_active ? 'Desactivar' : 'Activar'}
								</button>
							</form>
							<form method="POST" action="?/delete" use:enhance>
								<input type="hidden" name="id" value={keyword.id} />
								<button
									type="submit"
									class="text-link"
									aria-label="Eliminar {keyword.text}"
								>
									Eliminar
								</button>
							</form>
						</div>
					</td>
				</tr>
			{:else}
				<tr>
					<td colspan="5" class="config-rss-empty">
						Sin palabras clave. Añade el primer término.
					</td>
				</tr>
			{/each}
		</tbody>
	</table>
</div>

<!-- Mockup note, adapted to our product: the summary focus is the principal
     person (Operación), not a per-keyword focus button. -->
<p class="config-keyword-note">
	El foco del resumen se configura en Operación (persona principal); las palabras clave amplían
	la búsqueda.
</p>
