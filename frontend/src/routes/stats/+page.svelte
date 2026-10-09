<script lang="ts">
	import Chart from 'chart.js/auto';
	import {
		classificationLabel,
		formatDayLabel,
		formatDisplayDateTime,
		sentimentLabel,
		sourceLabel
	} from '$lib/format';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	const sentimentRows = $derived(
		(['positive', 'negative', 'neutral', 'null'] as const).map((key) => ({
			key,
			label: sentimentLabel(key === 'null' ? null : key),
			count: data.stats.by_sentiment[key] ?? 0
		}))
	);

	// Political classifier block (v1); absent until the backfill/worker ran.
	const political = $derived(
		data.stats.classifications?.find((c) => c.classifier === 'political')
	);
	const politicalTotal = $derived(political?.total_classified ?? 0);
	const politicalRows = $derived(
		Object.entries(political?.breakdown ?? {})
			.sort((a, b) => b[1] - a[1])
			.map(([label, count]) => ({
				label,
				text: classificationLabel(label),
				count,
				pct: politicalTotal > 0 ? Math.round((count / politicalTotal) * 100) : 0
			}))
	);
	const politicalPct = $derived(
		politicalRows.find((row) => row.label === 'political')?.pct ?? 0
	);

	const sourceRows = $derived(
		Object.entries(data.stats.by_source)
			.sort((a, b) => b[1] - a[1])
			.map(([source, count]) => ({ source, label: sourceLabel(source), count }))
	);
	const maxSourceCount = $derived(Math.max(1, ...sourceRows.map((row) => row.count)));

	// Spike markers (social-listening core): UTC day strings with >= 1 event.
	const spikeDays = $derived(new Set(data.spikes.map((spike) => spike.window_start.slice(0, 10))));
	const SPIKE_BAR = 'rgba(217, 119, 6, 0.9)';
	const BASE_BAR = 'rgba(2, 132, 199, 0.75)';

	const kpis = $derived([
		{ label: 'Total de menciones', value: data.stats.total },
		{ label: 'Últimas 24 horas', value: data.stats.last_24h },
		{ label: 'Últimos 7 días', value: data.stats.last_7d }
	]);

	// Sentiment palette; unclassified stays visually quiet (outline gray).
	const SENTIMENT_COLORS: Record<string, string> = {
		positive: '#16a34a',
		negative: '#dc2626',
		neutral: '#94a3b8',
		null: '#e2e8f0'
	};

	// Political palette: the positive label carries the accent color.
	const POLITICAL_COLORS: Record<string, string> = {
		political: '#0284c7',
		not_political: '#cbd5e1'
	};

	let volumeCanvas: HTMLCanvasElement | undefined = $state();
	let sentimentCanvas: HTMLCanvasElement | undefined = $state();
	let politicalCanvas: HTMLCanvasElement | undefined = $state();

	$effect(() => {
		if (!volumeCanvas) return;
		const chart = new Chart(volumeCanvas, {
			type: 'bar',
			data: {
				labels: data.stats.daily_volume.map((point) => formatDayLabel(point.date)),
				datasets: [
					{
						label: 'Menciones',
						data: data.stats.daily_volume.map((point) => point.count),
						// Amber bars mark days with a detected spike.
						backgroundColor: data.stats.daily_volume.map((point) =>
							spikeDays.has(point.date) ? SPIKE_BAR : BASE_BAR
						),
						hoverBackgroundColor: data.stats.daily_volume.map((point) =>
							spikeDays.has(point.date) ? '#b45309' : 'rgba(2, 132, 199, 1)'
						),
						borderRadius: 4,
						maxBarThickness: 28
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				plugins: { legend: { display: false } },
				scales: {
					y: { beginAtZero: true, ticks: { precision: 0 }, grid: { color: '#f1f5f9' } },
					x: { grid: { display: false } }
				}
			}
		});
		return () => chart.destroy();
	});

	$effect(() => {
		if (!sentimentCanvas) return;
		const chart = new Chart(sentimentCanvas, {
			type: 'doughnut',
			data: {
				labels: sentimentRows.map((row) => row.label),
				datasets: [
					{
						data: sentimentRows.map((row) => row.count),
						backgroundColor: sentimentRows.map((row) => SENTIMENT_COLORS[row.key]),
						borderWidth: 1,
						borderColor: '#ffffff'
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '62%',
				plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } }
			}
		});
		return () => chart.destroy();
	});

	$effect(() => {
		if (!politicalCanvas || politicalRows.length === 0) return;
		const chart = new Chart(politicalCanvas, {
			type: 'doughnut',
			data: {
				labels: politicalRows.map((row) => row.text),
				datasets: [
					{
						data: politicalRows.map((row) => row.count),
						backgroundColor: politicalRows.map(
							(row) => POLITICAL_COLORS[row.label] ?? '#94a3b8'
						),
						borderWidth: 1,
						borderColor: '#ffffff'
					}
				]
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				cutout: '62%',
				plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, padding: 16 } } }
			}
		});
		return () => chart.destroy();
	});
</script>

<svelte:head>
	<title>Estadísticas | Media Monitor</title>
</svelte:head>

<h1 class="text-2xl font-semibold tracking-tight">Estadísticas</h1>

<div class="mt-6 grid gap-4 sm:grid-cols-3">
	{#each kpis as kpi (kpi.label)}
		<div class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
			<p class="text-sm text-slate-500">{kpi.label}</p>
			<p class="mt-1 text-3xl font-semibold tabular-nums">{kpi.value}</p>
		</div>
	{/each}
</div>

<div class="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
	{#each sentimentRows as row (row.key)}
		<div class="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
			<div class="flex items-center gap-2">
				<span
					class="inline-block size-2.5 rounded-full ring-1 ring-slate-200"
					style={`background: ${SENTIMENT_COLORS[row.key]}`}
				></span>
				<p class="text-sm text-slate-500">{row.label}</p>
			</div>
			<p class="mt-1 text-2xl font-semibold tabular-nums">{row.count}</p>
		</div>
	{/each}
</div>

<div class="mt-4 grid gap-4 lg:grid-cols-3">
	<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm lg:col-span-2">
		<h2 class="text-sm font-semibold text-slate-700">Volumen diario (últimos 30 días)</h2>
		<div class="relative mt-4 h-72" role="img" aria-label="Volumen diario de menciones">
			<canvas bind:this={volumeCanvas}></canvas>
		</div>
		<p class="mt-2 flex items-center gap-1.5 text-xs text-slate-400">
			<span class="inline-block size-2 rounded-sm" style={`background: ${SPIKE_BAR}`}></span>
			día con pico detectado (saved searches)
		</p>
	</section>

	<section class="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
		<h2 class="text-sm font-semibold text-slate-700">Sentimiento</h2>
		<div class="relative mt-4 h-72" role="img" aria-label="Distribución por sentimiento">
			<canvas bind:this={sentimentCanvas}></canvas>
		</div>
	</section>
</div>

<section class="mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
	<h2 class="text-sm font-semibold text-slate-700">Spikes (últimos 30 días)</h2>
	{#if data.spikes.length === 0}
		<p class="mt-3 text-sm text-slate-500">
			Sin picos detectados: aparecen cuando una búsqueda guardada supera su baseline.
		</p>
	{:else}
		<ul class="mt-4 space-y-3">
			{#each data.spikes as spike (spike.id)}
				<li class="rounded-lg border border-amber-200 bg-amber-50/60 p-3">
					<div class="flex flex-wrap items-baseline justify-between gap-2">
						<p class="text-sm font-medium text-slate-800">{spike.saved_search_name}</p>
						<p class="text-xs tabular-nums text-slate-500">
							{formatDisplayDateTime(spike.window_start)} · {spike.count} menciones · z =
							{spike.zscore.toFixed(1)}
						</p>
					</div>
					<p class="mt-1 text-sm text-slate-600">
						{spike.summary ?? 'Resumen pendiente (sin proveedor de IA configurado o fallo transitorio).'}
					</p>
				</li>
			{/each}
		</ul>
	{/if}
</section>

<section class="mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
	<div class="flex flex-wrap items-baseline justify-between gap-2">
		<h2 class="text-sm font-semibold text-slate-700">Clasificaciones</h2>
		{#if political}
			<p class="text-xs text-slate-500">
				{politicalTotal}
				{politicalTotal === 1 ? 'mención clasificada' : 'menciones clasificadas'}
				· {politicalPct}% políticas
			</p>
		{/if}
	</div>
	{#if politicalTotal === 0}
		<p class="mt-3 text-sm text-slate-500">
			Sin clasificaciones todavía: ejecuta el backfill o espera al próximo ciclo de ingesta.
		</p>
	{:else}
		<div class="mt-4 grid gap-6 sm:grid-cols-2">
			<div class="relative h-64" role="img" aria-label="Distribución de la clasificación política">
				<canvas bind:this={politicalCanvas}></canvas>
			</div>
			<ul class="space-y-3 self-center">
				{#each politicalRows as row (row.label)}
					<li>
						<div class="flex items-baseline justify-between gap-4 text-sm">
							<span class="font-medium text-slate-700">{row.text}</span>
							<span class="tabular-nums text-slate-500">
								{row.count} · {row.pct}%
							</span>
						</div>
						<div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
							<div
								class="h-full rounded-full"
								style={`width: ${row.pct}%; background: ${POLITICAL_COLORS[row.label] ?? '#94a3b8'}`}
							></div>
						</div>
					</li>
				{/each}
			</ul>
		</div>
	{/if}
</section>

<section class="mt-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
	<h2 class="text-sm font-semibold text-slate-700">Por fuente</h2>
	{#if sourceRows.length === 0}
		<p class="mt-3 text-sm text-slate-500">Sin datos todavía.</p>
	{:else}
		<ul class="mt-4 space-y-3">
			{#each sourceRows as row (row.source)}
				<li>
					<div class="flex items-baseline justify-between gap-4 text-sm">
						<span class="font-medium text-slate-700">{row.label}</span>
						<span class="tabular-nums text-slate-500">{row.count}</span>
					</div>
					<div class="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100">
						<div
							class="h-full rounded-full bg-slate-900"
							style={`width: ${Math.round((row.count / maxSourceCount) * 100)}%`}
						></div>
					</div>
				</li>
			{/each}
		</ul>
	{/if}
</section>
