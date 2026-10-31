<script lang="ts">
	/**
	 * Un turno de consulta, forma mockup (`ask()`): burbuja de la pregunta,
	 * bloque `.answer` y una tarjeta `.evidence` real por cita. Compartido por
	 * la página /consultas y el panel flotante del layout para que ambas
	 * rendericen exactamente la misma anatomía y marcado.
	 */
	import type { ChatCitation } from '$lib/chat-history';
	import { formatDisplayDateTime, sentimentLabel, sourceLabel } from '$lib/format';

	let {
		question,
		answer = null,
		citations = [],
		pending = false,
		error = null
	}: {
		question: string;
		answer?: string | null;
		citations?: readonly ChatCitation[];
		pending?: boolean;
		error?: string | null;
	} = $props();
</script>

<div class="query-question">
	<span>Tu pregunta</span>
	<p>{question}</p>
</div>
{#if pending}
	<p class="thinking" role="status">Pensando…</p>
{/if}
{#if error}
	<p class="query-error" role="alert">{error}</p>
{:else if answer !== null}
	<article class="answer">
		<h3>Respuesta</h3>
		<p>{answer}</p>
	</article>
	{#each citations as citation, index (citation.url + (citation.title ?? ''))}
		<div class="evidence">
			<strong>[{index + 1}] {citation.source ? sourceLabel(citation.source) : 'Fuente'}</strong>
			<p>{citation.title ?? citation.url}</p>
			<a class="text-link" href={citation.url} target="_blank" rel="noopener noreferrer">
				Abrir evidencia #{citation.mention_id}
			</a>
			{#if citation.published_at}
				<span class="small muted">
					{formatDisplayDateTime(citation.published_at)}{#if citation.sentiment}
						· {sentimentLabel(citation.sentiment)}{/if}
				</span>
			{/if}
		</div>
	{/each}
{/if}
