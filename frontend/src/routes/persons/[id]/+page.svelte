<script lang="ts">
	import {
		displayDayKey,
		formatDisplayDateTime,
		formatDisplayTime,
		formatLongDate,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import type { PersonDetail } from '$lib/api';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const person = $derived(data.person);

	const sentimentCounts = $derived.by(() => {
		const counts: Record<string, number> = { positive: 0, negative: 0, neutral: 0 };
		for (const item of person.timeline) {
			if (item.sentiment) counts[item.sentiment] += 1;
		}
		return counts;
	});

	/** Timeline rows grouped by local calendar day; server order kept inside each day. */
	const mentionsByDay = $derived.by(() => {
		const days: Array<{ key: string; items: PersonDetail['timeline'] }> = [];
		const index = new Map<string, number>();
		for (const item of person.timeline) {
			const key = displayDayKey(item.published_at ?? item.ingested_at);
			const at = index.get(key);
			if (at === undefined) {
				index.set(key, days.length);
				days.push({ key, items: [item] });
			} else {
				days[at].items.push(item);
			}
		}
		return days;
	});
</script>

<svelte:head>
	<title>{person.name} | Media Monitor</title>
</svelte:head>

<a href="/persons" class="text-sm font-medium text-muted transition-colors hover:text-ink">
	← Volver a personajes
</a>

<header class="person-head">
	<p class="eyebrow">Actor</p>
	<h1 class="page-title">{person.name}</h1>
	{#if person.role || person.org}
		<p class="lead">
			{[person.role, person.org].filter(Boolean).join(' · ')}
		</p>
	{/if}
	{#if person.aliases.length > 0}
		<p class="person-aliases">También mencionado como: {person.aliases.join(', ')}</p>
	{/if}
</header>

<div class="grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Estadísticas históricas de menciones">
	<div class="profile-stat">
		<strong>{person.mention_count}</strong>
		<span>Menciones totales</span>
	</div>
	{#each Object.entries(sentimentCounts) as [sentiment, count] (`${sentiment}-${count}`)}
		<div class={`profile-stat ${sentiment}-stat`}>
			<strong>{count}</strong>
			<span>
				{sentiment === 'positive' ? 'Positivas' : sentiment === 'negative' ? 'Negativas' : 'Neutras'}
			</span>
		</div>
	{/each}
</div>

<dl class="directory-detail-meta">
	<div>
		<dt>Primera mención</dt>
		<dd>{formatDisplayDateTime(person.first_seen_at)}</dd>
	</div>
	<div>
		<dt>Última mención</dt>
		<dd>{formatDisplayDateTime(person.last_seen_at)}</dd>
	</div>
</dl>

<section class="person-timeline" aria-labelledby="person-timeline-title">
	<h2 id="person-timeline-title">Cronología de menciones</h2>
	<p class="support" role="status" aria-live="polite">
		{person.timeline.length}
		{person.timeline.length === 1 ? 'mención registrada' : 'menciones registradas'}
	</p>
	{#if person.timeline.length === 0}
		<p class="empty mt-4">Sin menciones registradas.</p>
	{:else}
		<div class="mention-timeline">
			{#each mentionsByDay as day (day.key)}
				<section class="mention-day">
					<h3 class="mention-day-title">
						<time datetime={day.key}>{formatLongDate(day.key)}</time>
						<span>{day.items.length} {day.items.length === 1 ? 'mención' : 'menciones'}</span>
					</h3>
					<ol class="mention-timeline-list">
						{#each day.items as item (item.mention_id)}
							<li class="mention-timeline-item">
								<div class="mention-timeline-stamp">
									<span class="mention-timeline-dot" aria-hidden="true"></span>
									<time datetime={item.published_at ?? item.ingested_at}>
										{formatDisplayTime(item.published_at ?? item.ingested_at)}
									</time>
								</div>
								<article class="mention-timeline-content">
									<div class="mention-badges">
										<span class="source-badge">{sourceLabel(item.source)}</span>
										{#if item.sentiment}
											<span class={`tone-badge tone-${item.sentiment}`}
												>{sentimentLabel(item.sentiment)}</span
											>
										{/if}
									</div>
									<h4>
										<a
											href={item.url}
											target="_blank"
											rel="noopener noreferrer"
											aria-label={`${item.title ?? item.url} (abre en una pestaña nueva)`}
										>
											{item.title ?? item.url}
										</a>
									</h4>
									{#if item.role}
										<p class="mention-role">Como: {item.role}</p>
									{/if}
									{#if item.context}
										<blockquote class="directory-quote">{item.context}</blockquote>
									{/if}
									{#if item.event_id && item.event_title}
										<p class="event-ref">
											<strong>Evento:</strong>
											<a
												href={`/events/${item.event_id}`}
												class="text-accent hover:text-accent-hover"
											>
												{item.event_title}
											</a>
										</p>
									{/if}
								</article>
							</li>
						{/each}
					</ol>
				</section>
			{/each}
		</div>
	{/if}
</section>

<p class="directory-disclaimer">
	Los recuentos corresponden al histórico completo del cliente; el timeline refleja las menciones
	vinculadas al personaje durante el enriquecimiento.
</p>
