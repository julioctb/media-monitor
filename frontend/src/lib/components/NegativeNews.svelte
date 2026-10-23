<script lang="ts">
	import { formatDateLong, sourceLabel } from '$lib/format';

	import type { NegativeNewsItem } from '$lib/digest-stats';

	let { items = [], day }: { items?: NegativeNewsItem[]; day: string } = $props();

	/** Editorial cap: the mockup shows at most three, total in the chip. */
	const VISIBLE_MAX = 3;
	const visible = $derived(items.slice(0, VISIBLE_MAX));
</script>

{#if visible.length > 0}
	<section class="negative-summary" aria-labelledby="negative-news-heading">
		<div class="negative-heading">
			<h2 id="negative-news-heading">Noticias negativas</h2>
			<span class="negative-count">
				{items.length}
				{items.length === 1 ? 'noticia' : 'noticias'}
			</span>
		</div>
		<ul aria-label="Noticias con sentimiento negativo">
			{#each visible as item (item.event_id)}
				<li>
					<span class="negative-source">
						{item.source ? sourceLabel(item.source) : 'Fuente no registrada'}{item.published_at
							? ` · ${formatDateLong(item.published_at)}`
							: ''}
					</span>
					<a
						href={`/feed?since=${day}&until=${day}`}
						aria-label={`${item.title}. Ver en el feed de noticias`}
					>
						{item.title}
					</a>
				</li>
			{/each}
		</ul>
		{#if items.length > visible.length}
			<p class="negative-context">
				Se muestran {visible.length} de {items.length} noticias negativas del día.
			</p>
		{/if}
	</section>
{/if}
