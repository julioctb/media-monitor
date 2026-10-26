<script lang="ts">
	import type { DailySummaryContent } from '$lib/api';

	import { createEvidenceContext, type EvidenceContext } from '$lib/digest-evidence';
	import { digestV3View } from '$lib/digest-v3';
	import BriefPanel from '$lib/components/BriefPanel.svelte';
	import TarjetaCard from '$lib/components/TarjetaCard.svelte';

	/**
	 * Container for the digest-brief-v3 render: detects the v3 keys on the
	 * stored content and composes brief + evidencia. Legacy v2 rows produce
	 * no view and this renders nothing — the home keeps its layout. Campo
	 * lives in its own surface (/campo); the digest no longer renders it (F4).
	 */
	let { content, context, narrative }: { content: DailySummaryContent; context?: EvidenceContext; narrative?: string } = $props();
  const evidenceContext = $derived(context ?? createEvidenceContext(content));

	const view = $derived(digestV3View(content));
	const tarjetas = $derived(
		view?.tarjetas.filter((tarjeta) => tarjeta.titulo || tarjeta.hecho || tarjeta.porQue || tarjeta.anguloNuevo || tarjeta.notas?.length) ?? []
	);
	const brief = $derived.by(() => {
		if (!view) return null;
		const empty =
			!view.headline &&
			view.delta.length === 0 &&
			view.riesgos.length === 0 &&
			view.decisiones.length === 0 &&
			view.ruido.length === 0 &&
			view.aFavor.length === 0 &&
			view.fechas.length === 0 &&
			view.vigilancia.length === 0 &&
			!view.descarte;
		return empty
			? null
			: {
					headline: view.headline,
					delta: view.delta,
					riesgos: view.riesgos,
					decisiones: view.decisiones,
					ruido: view.ruido,
					aFavor: view.aFavor,
					fechas: view.fechas,
					vigilancia: view.vigilancia,
					descarte: view.descarte
				};
	});
</script>

{#if view}
	{#if brief}
		<BriefPanel
      context={evidenceContext}
      headlineRequest={{ target: content, field: 'headline', text: narrative ?? null }}
			headline={narrative?.trim() ? narrative : brief.headline}
			delta={brief.delta}
			riesgos={brief.riesgos}
			decisiones={brief.decisiones}
			ruido={brief.ruido}
			aFavor={brief.aFavor}
			fechas={brief.fechas}
			vigilancia={brief.vigilancia}
			descarte={brief.descarte}
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
					<TarjetaCard {tarjeta} context={evidenceContext} />
				{/each}
			</div>
		</section>
	{/if}
{/if}
