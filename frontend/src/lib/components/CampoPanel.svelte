<script lang="ts">
	import { formatDisplayDateTime } from '$lib/format';

	import type { CampoView } from '$lib/digest-v3';

	/** Field reports of the window; the workflow estado is always visible. */
	let { entradas }: { entradas: CampoView[] } = $props();

	function cuandoLabel(value: string | null): string | null {
		if (!value) return null;
		const formatted = formatDisplayDateTime(value);
		return formatted && formatted !== '—' ? formatted : value;
	}

	/** Lugar · cuando line; null when the entry carries neither. */
	function referencia(entrada: CampoView): string | null {
		const partes = [entrada.lugar, cuandoLabel(entrada.cuando)].filter(
			(parte): parte is string => !!parte
		);
		return partes.length > 0 ? partes.join(' · ') : null;
	}
</script>

<section class="section digest-campo" aria-labelledby="digest-campo-heading">
	<header class="section-heading">
		<h2 id="digest-campo-heading">Campo</h2>
		<span class="section-note">
			{entradas.length}
			{entradas.length === 1 ? 'reporte en la ventana' : 'reportes en la ventana'}
		</span>
	</header>
	<ul class="digest-campo-list">
		{#each entradas as entrada, i (`campo-${i}`)}
			<li>
				<div class="digest-campo-head">
					<strong>{entrada.titulo}</strong>
					<span class="tag" class:positive={entrada.estado.toLowerCase() === 'publicada'}>
						{entrada.estado}
					</span>
				</div>
				{#if entrada.contenido}<p>{entrada.contenido}</p>{/if}
				{#if referencia(entrada)}<p class="daily-detail-source">{referencia(entrada)}</p>{/if}
			</li>
		{/each}
	</ul>
</section>
