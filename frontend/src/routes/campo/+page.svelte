<script lang="ts">
	let { data, form } = $props();

	import type { FieldReportRecord } from '$lib/api';
	import { sourceLabel } from '$lib/format';

	type Report = FieldReportRecord;

	const pending = $derived(data.pending as Report[]);
	const recent = $derived(data.recent as Report[]);

	function statusLabel(status: Report['status']): string {
		const labels: Record<Report['status'], string> = {
			draft: 'borrador',
			review: 'en revisión',
			published: 'publicado',
			rejected: 'rechazado'
		};
		return labels[status] ?? status;
	}

	function when(iso: string | null): string {
		if (!iso) return 'sin fecha';
		return new Date(iso).toLocaleString('es-MX', {
			dateStyle: 'medium',
			timeStyle: 'short'
		});
	}
</script>

<header class="page-header">
	<h1>Reportes de campo</h1>
	<p class="page-sub">
		Cola de revisión del canal humano: lo que carga la gente en territorio antes de
		entrar al feed. Publicar crea la mención con fuente «Reporte de campo».
	</p>
</header>

{#if form?.message}
	<p class="mt-2 text-xs {form.ok ? 'text-success' : 'text-danger'}" role="status">
		{form.message}
	</p>
{/if}

<section class="section" aria-labelledby="campo-pending">
	<div class="section-heading">
		<h2 id="campo-pending">En revisión ({pending.length})</h2>
	</div>
	{#if pending.length === 0}
		<p class="empty">Sin reportes pendientes: la cola está limpia.</p>
	{:else}
		<ul class="revisions-list">
			{#each pending as report (report.id)}
				<li class="revision-card">
					<header class="revision-meta">
						<span class="revision-seq">#{report.id}</span>
						<span class="revision-mode">{statusLabel(report.status)}</span>
						{#if report.happened_at}
							<span>{when(report.happened_at)}</span>
						{/if}
						{#if report.place}
							<span>{report.place}</span>
						{/if}
					</header>
					<p class="revision-title">{report.title ?? '(sin título)'}</p>
					<p class="revision-text">{report.content ?? '(sin contenido)'}</p>

					{#if report.enrichment}
						{@const suggestion = report.enrichment}
						<p class="mt-2 text-xs text-success">
							Sugerencia IA{#if suggestion.duplicate} · posible duplicado{/if}:
							“{suggestion.suggested_title}” — {suggestion.summary}
							{#if suggestion.tone}(tono: {suggestion.tone}){/if}
						</p>
					{/if}

					<details class="campo-edit">
						<summary>Editar</summary>
						<form method="post" action="?/update" class="mt-2 grid gap-2">
							<input type="hidden" name="id" value={report.id} />
							<input
								type="text"
								name="title"
								value={report.title ?? ''}
								placeholder="Título"
								class="w-full rounded border px-3 py-2"
							/>
							<textarea
								name="content"
								rows="3"
								placeholder="Contenido"
								class="w-full rounded border px-3 py-2">{report.content ?? ''}</textarea
							>
							<input
								type="text"
								name="place"
								value={report.place ?? ''}
								placeholder="Lugar"
								class="w-full rounded border px-3 py-2"
							/>
							<button type="submit" class="btn-primary min-h-[44px] rounded-full border px-4 text-sm font-semibold">
								Guardar cambios
							</button>
						</form>
					</details>

					<footer class="mt-3 flex gap-2">
						<form method="post" action="?/approve">
							<input type="hidden" name="id" value={report.id} />
							<button
								type="submit"
								class="min-h-[44px] rounded-full border border-accent bg-accent px-4 text-sm font-semibold text-accent-on"
							>
								Aprobar y publicar
							</button>
						</form>
						<form method="post" action="?/reject" class="flex flex-1 gap-2">
							<input type="hidden" name="id" value={report.id} />
							<input
								type="text"
								name="note"
								placeholder="Motivo (opcional)"
								class="min-h-[44px] flex-1 rounded border px-3"
							/>
							<button
								type="submit"
								class="min-h-[44px] rounded-full border px-4 text-sm font-semibold"
							>
								Rechazar
							</button>
						</form>
					</footer>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<section class="section" aria-labelledby="campo-history">
	<div class="section-heading">
		<h2 id="campo-history">Historial reciente</h2>
	</div>
	{#if recent.length === 0}
		<p class="empty">Sin historia todavía.</p>
	{:else}
		<ul class="revisions-list">
			{#each recent as report (report.id)}
				<li class="revision-card">
					<header class="revision-meta">
						<span class="revision-seq">#{report.id}</span>
						<span class="revision-mode">{statusLabel(report.status)}</span>
						<span>{sourceLabel('field_report')}</span>
						{#if report.published_at}
							<span>publicado {when(report.published_at)}</span>
						{/if}
					</header>
					<p class="revision-title">{report.title ?? '(sin título)'}</p>
					{#if report.review_note}
						<p class="revision-text">Nota: {report.review_note}</p>
					{/if}
				</li>
			{/each}
		</ul>
	{/if}
</section>
