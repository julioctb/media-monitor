<script lang="ts">
	import { cleanDigestText, sourceLabel } from '$lib/format';

	import DigestEvidence from './DigestEvidence.svelte';
	import { storyEvidence, type EvidenceContext } from '$lib/digest-evidence';
	import type { TarjetaView } from '$lib/digest-v3';

	/** One evidence card: hecho, por qué, fuentes and the repeat/tono badges. */
	let { tarjeta, context }: { tarjeta: TarjetaView; context?: EvidenceContext } = $props();

	const tonoClass = $derived(
		tarjeta.tono === 'positivo' ? 'positive' : tarjeta.tono === 'negativo' ? 'negative' : ''
	);
	const fuentesLine = $derived(
		tarjeta.fuentes.length > 0
			? `Fuente: ${[...new Set(tarjeta.fuentes.map((fuente) => sourceLabel(fuente)))].join(' · ')}`
			: null
	);
</script>

<article class="digest-tarjeta">
	<header class="digest-tarjeta-head">
		{#if tarjeta.titulo}<h3>{tarjeta.titulo}</h3>{/if}
		<div class="digest-tarjeta-badges">
			{#if tarjeta.tono}
				<span class="tag {tonoClass}">{tarjeta.tono}</span>
			{/if}
			{#if tarjeta.repeat}
				<span class="tag">Reiteración</span>
			{/if}
		</div>
	</header>
	{#if tarjeta.hecho}<p class="digest-tarjeta-hecho">{cleanDigestText(tarjeta.hecho)}</p><DigestEvidence {context} request={storyEvidence(tarjeta.raw, tarjeta.raw?.hecho == null ? 'summary' : 'hecho')} />{/if}
	{#if tarjeta.porQue}
		<p class="digest-tarjeta-porque"><strong>Por qué</strong> — {cleanDigestText(tarjeta.porQue)}</p><DigestEvidence {context} request={storyEvidence(tarjeta.raw, 'por_que')} />
	{/if}
	{#if tarjeta.anguloNuevo}
		<p class="digest-tarjeta-angulo">
			<strong>Ángulo nuevo</strong> — {cleanDigestText(tarjeta.anguloNuevo)}
		</p><DigestEvidence {context} request={storyEvidence(tarjeta.raw, 'angulo_nuevo')} />
	{/if}
  {#if tarjeta.notas?.length}
    <ul class="digest-tarjeta-notas">
      {#each tarjeta.notas as nota (nota.position)}
        <li>{cleanDigestText(nota.text)}<DigestEvidence {context} request={storyEvidence(tarjeta.raw, 'notas', nota.position)} /></li>
      {/each}
    </ul>
  {/if}
	{#if fuentesLine}<p class="daily-detail-source">{fuentesLine}</p>{/if}
</article>
