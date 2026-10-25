<script lang="ts">
	import type { BriefFechaView } from '$lib/digest-v3';

	interface BriefEntry {
		titulo: string;
		razon: string | null;
		/** F6 afectacion line; null when the entry carries none. */
		afectacion: string | null;
	}

	interface VigilanciaLinea {
		persona: string;
		nota: string | null;
		fecha: string;
		afectacion: string | null;
	}

	/**
	 * Presentational brief panel (dark hero, the narrative band's successor):
	 * fixed sections, each gated on real data — an absent section renders
	 * nothing, never a placeholder.
	 */
	let {
		headline = null,
		delta = [],
		riesgos = [],
		decisiones = [],
		ruido = [],
		aFavor = [],
		fechas = [],
		vigilancia = [],
		descarte = null
	}: {
		headline?: string | null;
		delta?: string[];
		riesgos?: BriefEntry[];
		decisiones?: BriefEntry[];
		ruido?: BriefEntry[];
		aFavor?: BriefEntry[];
		fechas?: BriefFechaView[];
		vigilancia?: VigilanciaLinea[];
		/** F3 visible-discard line; null renders nothing. */
		descarte?: string | null;
	} = $props();

	const secciones: {
		titulo: string;
		entradas: { principal: string; secundario: string | null; extra: string | null }[];
	}[] = $derived.by(() => {
		const pick = (entries: BriefEntry[]) =>
			entries.map((entry) => ({
				principal: entry.titulo,
				secundario: entry.razon,
				extra: entry.afectacion
			}));
		const bloques: {
			titulo: string;
			entradas: { principal: string; secundario: string | null; extra: string | null }[];
		}[] = [];
		if (delta.length > 0) {
			bloques.push({
				titulo: 'Qué cambió',
				entradas: delta.map((linea) => ({ principal: linea, secundario: null, extra: null }))
			});
		}
		// F5: riesgo primero, luego decisión; el resto por impacto y el
		// ruido al final vive en el orden de las tarjetas.
		if (riesgos.length > 0) {
			bloques.push({ titulo: 'Riesgo', entradas: pick(riesgos) });
		}
		if (decisiones.length > 0) {
			bloques.push({ titulo: 'Decisión / atención', entradas: pick(decisiones) });
		}
		if (aFavor.length > 0) {
			bloques.push({ titulo: 'A favor', entradas: pick(aFavor) });
		}
		if (ruido.length > 0) {
			bloques.push({ titulo: 'Ruido', entradas: pick(ruido) });
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
							{#if entrada.extra}<span class="digest-brief-afectacion">{entrada.extra}</span>{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/each}
		{#if vigilancia.length > 0}
			<div class="digest-brief-block">
				<h3>Vigilancia</h3>
				<ul>
					{#each vigilancia as linea, i (`vigilancia-${i}`)}
						<li>
							<strong>{linea.persona}</strong>
							{#if linea.nota}: {linea.nota}{/if}
							{#if linea.fecha} <span class="digest-brief-estado">{linea.fecha}</span>{/if}
							{#if linea.afectacion}<span class="digest-brief-afectacion">{linea.afectacion}</span>{/if}
						</li>
					{/each}
				</ul>
			</div>
		{/if}
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