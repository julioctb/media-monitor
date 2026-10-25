<script lang="ts">
	import type { BriefFechaView } from '$lib/digest-v3';

	interface BriefEntry {
		titulo: string;
		razon: string | null;
	}

	/**
	 * Presentational brief panel (dark hero, the narrative band's successor):
	 * fixed sections, each gated on real data — an absent section renders
	 * nothing, never a placeholder.
	 */
	let {
		headline = null,
		delta = [],
		decisiones = [],
		ruido = [],
		aFavor = [],
		fechas = [],
		descarte = null
	}: {
		headline?: string | null;
		delta?: string[];
		decisiones?: BriefEntry[];
		ruido?: BriefEntry[];
		aFavor?: BriefEntry[];
		fechas?: BriefFechaView[];
		/** F3 visible-discard line; null renders nothing. */
		descarte?: string | null;
	} = $props();

	const secciones: { titulo: string; entradas: { principal: string; secundario: string | null }[] }[] =
		$derived.by(() => {
			const pick = (entries: BriefEntry[]) =>
				entries.map((entry) => ({ principal: entry.titulo, secundario: entry.razon }));
			const bloques: { titulo: string; entradas: { principal: string; secundario: string | null }[] }[] =
				[];
			if (delta.length > 0) {
				bloques.push({
					titulo: 'Qué cambió',
					entradas: delta.map((linea) => ({ principal: linea, secundario: null }))
				});
			}
			if (decisiones.length > 0) {
				bloques.push({ titulo: 'Decisión / atención', entradas: pick(decisiones) });
			}
			if (ruido.length > 0) {
				bloques.push({ titulo: 'Ruido', entradas: pick(ruido) });
			}
			if (aFavor.length > 0) {
				bloques.push({ titulo: 'A favor', entradas: pick(aFavor) });
			}
			return bloques;
		});
</script>

<section class="digest-brief" aria-labelledby="digest-brief-heading">
	<div class="eyebrow" id="digest-brief-heading">Brief del día</div>
	{#if headline}
		<p class="digest-brief-headline">{headline}</p>
	{/if}
	<div class="digest-brief-grid">
		{#each secciones as bloque (bloque.titulo)}
			<div class="digest-brief-block">
				<h3>{bloque.titulo}</h3>
				<ul>
					{#each bloque.entradas as entrada, i (`${bloque.titulo}-${i}`)}
						<li>
							<strong>{entrada.principal}</strong>
							{#if entrada.secundario}<span> — {entrada.secundario}</span>{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/each}
		{#if fechas.length > 0}
			<div class="digest-brief-block">
				<h3>Fechas que obligan</h3>
				<ul>
					{#each fechas as fecha, i (`fecha-${i}`)}
						<li>
							<span class="digest-brief-estado">{fecha.estado}</span>
							<strong>{fecha.titulo}</strong>
							{#if fecha.cuando}<span> ({fecha.cuando})</span>{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
	</div>
	{#if descarte}
		<p class="digest-brief-descarte">{descarte}</p>
	{/if}
</section>