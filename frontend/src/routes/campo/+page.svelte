<script lang="ts">
	let { data, form } = $props();

	import type { FieldOperatorRecord, FieldReportRecord } from '$lib/api';
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

<section class="section" aria-labelledby="campo-operators">
	<div class="section-heading">
		<h2 id="campo-operators">Acceso de operadores</h2>
	</div>
	<p class="mt-1 text-xs text-gray-500">
		Solo operadores activos pueden reportar al bot; los desconocidos quedan en lista de espera.
	</p>
	{#if (data.operators as FieldOperatorRecord[]).length === 0}
		<p class="empty">Sin operadores registrados todavía.</p>
	{:else}
		<ul class="mt-2 grid gap-2">
			{#each data.operators as operator (operator.id)}
				<li class="flex min-h-[44px] items-center justify-between gap-3 rounded border px-3 py-2">
					<div class="text-sm">
						<span class="font-semibold">{operator.display_name}</span>
						{#if operator.telegram_user_id}
							<span class="text-xs text-gray-500"> · tg {operator.telegram_user_id}</span>
						{/if}
						<span class={'text-xs ' + (operator.active ? 'text-success' : 'text-warning')}>
							· {operator.active ? 'activo' : 'en espera'}
						</span>
					</div>
					<form method="post" action={operator.active ? '?/deactivateOperator' : '?/activateOperator'}>
						<input type="hidden" name="id" value={operator.id} />
						<button
							type="submit"
							class="min-h-[44px] rounded-full border px-4 text-sm font-semibold"
						>
							{operator.active ? 'Desactivar' : 'Activar'}
						</button>
					</form>
				</li>
			{/each}
		</ul>
	{/if}
</section>

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
