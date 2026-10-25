<script lang="ts">
	import type { DailySummaryContent } from '$lib/api';

	import { digestV3View } from '$lib/digest-v3';
	import BriefPanel from '$lib/components/BriefPanel.svelte';
	import CampoPanel from '$lib/components/CampoPanel.svelte';
	import TarjetaCard from '$lib/components/TarjetaCard.svelte';

	/**
	 * Container for the digest-brief-v3 render: detects the v3 keys on the
	 * stored content and composes brief + evidencia + campo. Legacy v2 rows
	 * produce no view and this renders nothing — the home keeps its layout.
	 */
	let { content }: { content: DailySummaryContent } = $props();

	const view = $derived(digestV3View(content));
	const tarjetas = $derived(
		view?.tarjetas.filter((tarjeta) => tarjeta.titulo || tarjeta.hecho || tarjeta.porQue) ?? []
	);
	const brief = $derived.by(() => {
		if (!view) return null;
		const empty =
			!view.headline &&
			view.delta.length === 0 &&
			view.decisiones.length === 0 &&
			view.ruido.length === 0 &&
			view.aFavor.length === 0 &&
			view.fechas.length === 0;
		return empty
			? null
			: {
					headline: view.headline,
					delta: view.delta,
					decisiones: view.decisiones,
					ruido: view.ruido,
					aFavor: view.aFavor,
					fechas: view.fechas
				};
	});
</script>

{#if view}
	{#if brief}
		<BriefPanel
			headline={brief.headline}
			delta={brief.delta}
			decisiones={brief.decisiones}
			ruido={brief.ruido}
			aFavor={brief.aFavor}
			fechas={brief.fechas}
		/>
	{/if}
	{#if tarjetas.length > 0}
		<section class="section digest-evidencia" aria-labelledby="digest-evidencia-heading">
			<header class="section-heading">
				<h2 id="digest-evidencia-heading">Evidencia del día</h2>
				<span class="section-note">
					{tarjetas.length}
					{tarjetas.length === 1 ? 'historia documentada' : 'historias documentadas'}
				</span>
			</header>
			<div class="digest-tarjetas">
				{#each tarjetas as tarjeta, i (`tarjeta-${i}`)}
					<TarjetaCard {tarjeta} />
				{/each}
			</div>
		</section>
	{/if}
	{#if view.campo.length > 0}
		<CampoPanel entradas={view.campo} />
	{/if}
{/if}
