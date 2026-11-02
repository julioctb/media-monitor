<script lang="ts">
	import type { PersonDetail, PersonSummary } from '$lib/api';
	import { monogram } from '$lib/digest-stats';
	import { safeEvidenceUrl } from '$lib/digest-evidence';
	import {
		channelClassFor,
		formatDisplayDateTime,
		formatDisplayTime,
		formatLongDate,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import { ICON_PATHS } from '$lib/icons';
	import { groupPersonTimeline, PERSON_TIMELINE_PAGE_SIZE, personTimelinePage } from '$lib/persons';
	import { prefs, setFollowPerson } from '$lib/prefs';
	import { notifyPersist } from '$lib/toast.svelte';
	import DetailDialog from './DetailDialog.svelte';

	let { person, onclose }: { person: PersonSummary | null; onclose: () => void } = $props();
	let detail = $state.raw<PersonDetail | null>(null);
	let loading = $state(false);
	let failure = $state<string | null>(null);
	let requestedOffset = $state(0);
	let requestVersion = 0;

	const profile = $derived(detail ?? person);
	const followed = $derived(person ? $prefs.persons.includes(person.id) : false);
	const groups = $derived(detail ? groupPersonTimeline(detail.timeline) : []);
	const page = $derived(
		detail ? personTimelinePage(detail, { limit: PERSON_TIMELINE_PAGE_SIZE, offset: requestedOffset }) : null
	);
	const relatedEvents = $derived.by(() => {
		const events = new Map<number, string>();
		for (const item of detail?.timeline ?? []) {
			if (item.event_id && item.event_title) events.set(item.event_id, item.event_title);
		}
		return [...events];
	});

	$effect(() => {
		const id = person?.id;
		detail = null;
		failure = null;
		requestedOffset = 0;
		if (id) void loadPage(id, 0);
		else loading = false;
		// A closed or replaced identity must never receive an older response.
		return () => { requestVersion += 1; };
	});

	async function loadPage(id: number, offset: number) {
		const version = ++requestVersion;
		const nextOffset = Math.max(0, offset);
		requestedOffset = nextOffset;
		loading = true;
		failure = null;
		try {
			const params = new URLSearchParams({
				limit: String(PERSON_TIMELINE_PAGE_SIZE), offset: String(nextOffset), order: 'recent'
			});
			const response = await fetch(`/api/persons/${id}?${params.toString()}`);
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const next = (await response.json()) as PersonDetail;
			if (version === requestVersion) detail = next;
		} catch {
			if (version === requestVersion) {
				detail = null;
				failure = 'No se pudo cargar la ficha. Intenta de nuevo.';
			}
		} finally {
			if (version === requestVersion) loading = false;
		}
	}
</script>

<DetailDialog titleId="person-detail-title" title="Ficha de persona" open={person}
	variant="person-detail" closeOnBackdrop={true} {onclose}>
	{#if person && profile}
		<div class="directory-detail-heading">
			<span class="directory-monogram" aria-hidden="true">{monogram(profile.name)}</span>
			<div>
				<p class="daily-dialog-eyebrow">Persona · {profile.id}</p>
				<h2>{profile.name}</h2>
				{#if profile.role || profile.org}
					<p class="daily-dialog-meta">{[profile.role, profile.org].filter(Boolean).join(' · ')}</p>
				{/if}
			</div>
			<button type="button" class="button {followed ? 'primary' : ''}" aria-pressed={followed}
				onclick={() => notifyPersist(setFollowPerson(person.id, !followed))}>
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={followed ? ICON_PATHS.check : ICON_PATHS.bookmark} /></svg>
				{followed ? 'En seguimiento' : 'Seguir persona'}
			</button>
		</div>
		{#if profile.aliases.length > 0}
			<p class="person-aliases">También mencionado como: {profile.aliases.join(', ')}</p>
		{/if}
		<dl class="directory-detail-meta">
			<div><dt>Menciones</dt><dd>{profile.mention_count}</dd></div>
			<div><dt>Primera mención</dt><dd>{formatDisplayDateTime(profile.first_seen_at)}</dd></div>
			<div><dt>Última mención</dt><dd>{formatDisplayDateTime(profile.last_seen_at)}</dd></div>
		</dl>
		{#if !loading && relatedEvents.length > 0}
			<h3>Eventos de esta página</h3>
			<div class="chips">
				{#each relatedEvents as [eventId, title] (eventId)}
					<a class="chip event-chip" href={`/events/${eventId}`}>#{eventId} · {title}</a>
				{/each}
			</div>
		{/if}
		<section class="person-timeline" aria-labelledby="person-timeline-title">
			<h3 id="person-timeline-title">Cronología de menciones{#if page && page.total !== null}{' · '}{page.total}{/if}</h3>
			{#if loading}
				<p class="daily-empty-note" role="status">Cargando ficha…</p>
			{:else if failure}
				<p class="daily-dialog-warning" role="alert">{failure}</p>
			{:else if detail && detail.timeline.length === 0}
				<p class="daily-empty-note">Sin menciones registradas en esta página.</p>
			{:else if detail}
				<div class="mention-timeline">
					{#each groups as group (group.key)}
						<section class="mention-day">
							<h4 class="mention-day-title">
								<time datetime={group.key}>{formatLongDate(group.key)}</time>
								<span>{group.items.length} {group.items.length === 1 ? 'mención' : 'menciones'} en esta página</span>
							</h4>
							<ol class="mention-timeline-list">
								{#each group.items as item (item.mention_id)}
									{@const sourceUrl = safeEvidenceUrl(item.url)}
									<li class="mention-timeline-item">
										<div class="mention-timeline-stamp">
											<span class="mention-timeline-dot" aria-hidden="true"></span>
											<time datetime={item.published_at ?? item.ingested_at}>{formatDisplayTime(item.published_at ?? item.ingested_at)}</time>
										</div>
										<article class="mention-timeline-content">
											<div class="mention-badges">
												<span class={`source-badge ${channelClassFor(item.source)}`}>{sourceLabel(item.source)}</span>
												{#if item.sentiment}<span class={`tone-badge tone-${item.sentiment}`}>{sentimentLabel(item.sentiment)}</span>{/if}
											</div>
											<h4>{item.title?.trim() || item.url}</h4>
											{#if item.role || item.org}<p class="mention-role">Como: {[item.role, item.org].filter(Boolean).join(' · ')}</p>{/if}
											{#if item.context}<blockquote class="directory-quote">{item.context}</blockquote>{/if}
											{#if item.event_id && item.event_title}<p class="event-ref"><strong>Evento:</strong> <a href={`/events/${item.event_id}`}>{item.event_title}</a></p>{/if}
											{#if sourceUrl}<a class="text-link" href={sourceUrl} target="_blank" rel="noopener noreferrer">Leer registro original</a>{/if}
										</article>
									</li>
								{/each}
							</ol>
						</section>
					{/each}
				</div>
			{/if}
		</section>
		{#if page}
			<div class="directory-pagination">
				<span>Página {Math.floor(page.offset / page.limit) + 1}{#if page.total !== null}{' de '}{Math.max(1, Math.ceil(page.total / page.limit))}{/if}</span>
				<div class="od-row">
					<button class="button" type="button" disabled={!page.hasPrevious || loading} onclick={() => loadPage(person.id, page.offset - page.limit)}>Anterior</button>
					<button class="button" type="button" data-timeline-next disabled={!page.hasNext || loading} onclick={() => loadPage(person.id, page.offset + page.limit)}>Siguiente</button>
				</div>
			</div>
		{/if}
	{/if}
</DetailDialog>
