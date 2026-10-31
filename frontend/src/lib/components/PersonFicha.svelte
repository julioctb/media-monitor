<script lang="ts">
	import {
		displayDayKey,
		formatDisplayDateTime,
		formatDisplayTime,
		formatLongDate,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import { ICON_PATHS } from '$lib/icons';
	import type { PersonDetail } from '$lib/api';

	interface Props {
		person: PersonDetail;
		/** Followed id lives in mm_prefs (parent resolves membership). */
		followed: boolean;
		onToggleFollow: () => void;
		/** Page renders plain h1 (global h1 del kit); the dialog renders a plain h2 (mockup). */
		headingTag?: 'h1' | 'h2';
		headingClass?: string;
	}

	let {
		person,
		followed,
		onToggleFollow,
		headingTag = 'h1',
		headingClass = ''
	}: Props = $props();

	const sentimentCounts = $derived.by(() => {
		const counts: Record<string, number> = { positive: 0, negative: 0, neutral: 0 };
		for (const item of person.timeline) {
			if (item.sentiment) counts[item.sentiment] += 1;
		}
		return counts;
	});

	/** Mockup directoryDetail «Eventos relacionados»: distinct events across the full timeline. */
	const relatedEvents = $derived.by(() => {
		const byId = new Map<number, string>();
		for (const item of person.timeline) {
			if (item.event_id && item.event_title && !byId.has(item.event_id)) {
				byId.set(item.event_id, item.event_title);
			}
		}
		return [...byId.entries()];
	});

	/** Mockup directoryDetail: 25 menciones por página; the visible page groups by day. */
	const PAGE_SIZE = 25;
	let page = $state(1);
	const pages = $derived(Math.max(1, Math.ceil(person.timeline.length / PAGE_SIZE)));
	const currentPage = $derived(Math.min(page, pages));
	const pageMentions = $derived(
		person.timeline.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE)
	);

	/** Timeline rows grouped by local calendar day; server order kept inside each day. */
	const mentionsByDay = $derived.by(() => {
		const days: Array<{ key: string; items: PersonDetail['timeline'] }> = [];
		const index = new Map<string, number>();
		for (const item of pageMentions) {
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

<header class="person-head">
	<p class="eyebrow">Persona · {person.id}</p>
	<div class="directory-detail-heading">
		<svelte:element this={headingTag} class={headingClass || undefined}>{person.name}</svelte:element>
		<button
			type="button"
			class="button {followed ? 'primary' : ''}"
			aria-pressed={followed}
			onclick={onToggleFollow}
		>
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
				<path d={followed ? ICON_PATHS.check : ICON_PATHS.bookmark} />
			</svg>
			{followed ? 'En seguimiento' : 'Seguir persona'}
		</button>
	</div>
	{#if person.role || person.org}
		<p class="lead">
			{[person.role, person.org].filter(Boolean).join(' · ')}
		</p>
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
	{#if person.aliases.length > 0}
		<div>
			<dt>Variantes anotadas</dt>
			<dd>{person.aliases.join(', ')}</dd>
		</div>
	{/if}
</dl>

<h3>Eventos relacionados</h3>
<div class="chips">
	{#if relatedEvents.length > 0}
		{#each relatedEvents as [eventId, title] (eventId)}
			<a class="chip event-chip" href={`/events/${eventId}`}>#{eventId} · {title}</a>
		{/each}
	{:else}
		<p class="support">Estas menciones aún no están asociadas a un evento agrupado.</p>
	{/if}
</div>

<h3 class="directory-evidence-heading">Cronología de menciones · {person.timeline.length}</h3>
<p class="support">
	Más recientes primero · Horario local · {PAGE_SIZE} menciones por página
</p>
{#if person.timeline.length === 0}
	<p class="empty mt-4">Sin menciones registradas.</p>
{:else}
	<div class="mention-timeline">
		{#each mentionsByDay as day (day.key)}
			<section class="mention-day">
				<h3 class="mention-day-title">
					<time datetime={day.key}>{formatLongDate(day.key)}</time>
					<span
						>{day.items.length} {day.items.length === 1 ? 'mención' : 'menciones'} en esta
						página</span
					>
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
	<div class="directory-pagination">
		<span>Página {currentPage} de {pages}</span>
		<div class="od-row">
			<button
				type="button"
				class="button"
				disabled={currentPage === 1}
				onclick={() => (page = currentPage - 1)}
			>
				Anterior
			</button>
			<button
				type="button"
				class="button"
				disabled={currentPage >= pages}
				onclick={() => (page = currentPage + 1)}
			>
				Siguiente
			</button>
		</div>
	</div>
{/if}
