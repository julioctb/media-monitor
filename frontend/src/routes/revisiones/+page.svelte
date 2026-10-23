<script lang="ts">
	import { formatDisplayDateTimeLong, formatDateLong } from '$lib/format';

	import type { PageProps } from './$types';

	let {
		data,
		form
	}: {
		data: PageProps['data'];
		form: PageProps['form'];
	} = $props();

	const dayHref = (day: string) => `?day=${day}`;
	const selectedLabel = $derived(
		data.selectedDay
			? formatDateLong(`${data.selectedDay}T12:00:00Z`)
			: 'Sin día seleccionado'
	);
</script>

<svelte:head>
	<title>Revisiones | Media Monitor</title>
</svelte:head>

<header class="page-header">
	<h1>Revisiones de narrativa</h1>
	<p class="page-sub">
		Historial de cada síntesis generada por corte; restaura cualquier versión sin perder las
		demás.
	</p>
</header>

{#if data.days.length === 0}
	<section class="section">
		<p class="empty">Sin revisiones registradas todavía: aparecen con el primer corte.</p>
	</section>
{:else}
	<div class="revisions-layout">
		<aside class="revisions-days" aria-label="Días con revisiones">
			<h2>Días</h2>
			<ul>
				{#each data.days as dayRow (dayRow.summary_date)}
					<li>
						<a
							href={dayHref(dayRow.summary_date)}
							aria-current={data.selectedDay === dayRow.summary_date ? 'page' : undefined}
						>
							<span>{formatDateLong(`${dayRow.summary_date}T12:00:00Z`)}</span>
							<span class="revisions-count">{dayRow.count}</span>
						</a>
					</li>
				{/each}
			</ul>
		</aside>

		<section class="revisions-panel" aria-labelledby="revisions-day-heading">
			<h2 id="revisions-day-heading">{selectedLabel}</h2>
			{#if data.revisions.length === 0}
				<p class="empty">Este día no tiene revisiones registradas.</p>
			{:else}
				{#if form?.ok}
					<p class="revisions-flash ok" role="status">{form.message}</p>
				{:else if form && !form.ok}
					<p class="revisions-flash error" role="alert">{form.message}</p>
				{/if}
				<ol class="revisions-list">
					{#each data.revisions as revision (revision.seq)}
						<li class="revision-card">
							<header>
								<span class="revision-seq">#{revision.seq}</span>
								<span class="revision-mode">{revision.mode}</span>
								<time datetime={revision.created_at}>
									{formatDisplayDateTimeLong(revision.created_at)}
								</time>
							</header>
							<p class="revision-text">{revision.narrative}</p>
							<form method="POST" action="?/restore">
								<input type="hidden" name="day" value={revision.summary_date} />
								<input type="hidden" name="seq" value={revision.seq} />
								<button type="submit" class="revision-restore">Usar esta versión</button>
							</form>
						</li>
					{/each}
				</ol>
			{/if}
		</section>
	</div>
{/if}
