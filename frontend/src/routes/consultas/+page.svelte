<script lang="ts">
	import type { PageProps, SubmitFunction } from './$types';

	import { browser } from '$app/environment';
	import { enhance } from '$app/forms';

	import QueryAnswer from '$lib/components/QueryAnswer.svelte';
	import { ICON_PATHS } from '$lib/icons';
	import {
		appendTurn,
		createThread,
		loadThreads,
		saveThreads,
		threadTitle,
		type ChatCitation,
		type ChatThread
	} from '$lib/chat-history';
	import { formatDisplayTime } from '$lib/format';
	import { personDirectoryHref } from '$lib/persons';

	let { data, form: result }: PageProps = $props();

	let threads = $state<ChatThread[]>(browser ? loadThreads(localStorage) : []);
	let activeId = $state<string | null>(null);
	let processedTurn = $state(0);
	// The draft lives client-side: cleared on success, kept on error. The
	// server-echoed question (result.question) feeds the history, not the input.
	let draft = $state('');
	let pending = $state(false);
	let questionField: HTMLTextAreaElement | undefined;
	let scrollEl: HTMLDivElement | undefined;

	// Los chips del welcome vienen del digest diario real (loader); el click
	// rellena el composer y devuelve el foco para editar y enviar, como el
	// patrón de suggestion button del mockup (preguntas sugeridas).
	function applyPrompt(question: string) {
		draft = question;
		questionField?.focus();
	}

	const submitEnhance: SubmitFunction = () => {
		pending = true;
		return async ({ result, update }) => {
			pending = false;
			// Keep our own reset semantics: the effect below persists the turn
			// from `form`, and the draft is cleared only on a real answer.
			await update({ reset: false });
			if (result.type === 'success' && !result.data?.error) draft = '';
		};
	};

	const active = $derived(threads.find((thread) => thread.id === activeId) ?? null);

	// Persist every finished server turn into the local history once.
	$effect(() => {
		const turn = result?.turn;
		if (typeof turn !== 'number' || turn === processedTurn) return;
		processedTurn = turn;
		const question = String(result?.question ?? '').trim();
		if (!question) return;
		let thread = threads.find((candidate) => candidate.id === activeId);
		if (!thread) {
			thread = createThread();
			threads = [thread, ...threads];
			activeId = thread.id;
		}
		const updated = appendTurn(thread, {
			question,
			answer: result?.answer,
			citations: result?.citations,
			error: result?.error
		});
		threads = threads.map((candidate) => (candidate.id === updated.id ? updated : candidate));
		saveThreads(localStorage, threads);
	});

	interface Turn {
		question: string;
		answer: string | null;
		citations: ChatCitation[];
		error: string | null;
	}
	// Un turno = pregunta del usuario + su respuesta (assistant) o aviso de
	// error (notice), en el orden en que se guardaron.
	const turns = $derived.by<Turn[]>(() => {
		if (!active) return [];
		const out: Turn[] = [];
		for (const message of active.messages) {
			if (message.role === 'user') {
				out.push({ question: message.text, answer: null, citations: [], error: null });
			} else if (out.length > 0) {
				const last = out[out.length - 1];
				if (message.role === 'assistant') {
					last.answer = message.text;
					last.citations = message.citations ?? [];
				} else {
					last.error = message.text;
				}
			}
		}
		return out;
	});

	// El mockup hace scroll al inicio del scroll-area tras cada respuesta.
	let lastTurnAt = '';
	$effect(() => {
		const at = active?.updatedAt ?? '';
		if (!active || at === lastTurnAt) return;
		lastTurnAt = at;
		if (pending) return;
		// jsdom no implementa Element.scrollTo; el guard cubre ese caso.
		if (typeof scrollEl?.scrollTo === 'function') scrollEl.scrollTo({ top: 0 });
	});

	function startNewChat() {
		activeId = null;
		lastTurnAt = '';
	}

	function deleteThread(id: string) {
		threads = threads.filter((thread) => thread.id !== id);
		if (activeId === id) {
			activeId = null;
			lastTurnAt = '';
		}
		saveThreads(localStorage, threads);
	}
</script>

<svelte:head>
	<title>Consultas | Media Monitor</title>
</svelte:head>

<!-- Intro como el mockup: solo el h1 (su page-description está hidden en
     render()); sin la tarjeta .intro v2 (fondo/borde que el mockup no tiene). -->
<header class="page-header">
	<h1>Consultas</h1>
</header>

<div class="query-layout">
	<section class="panel query-box" class:has-answer={turns.length > 0} aria-labelledby="chat-heading">
		<header class="query-chat-header">
			<span class="query-chat-mark" aria-hidden="true">
				<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.query} /></svg>
			</span>
			<div>
				<h2 id="chat-heading">De la pregunta a la fuente</h2>
				<p>Consulta los registros del monitoreo</p>
			</div>
		</header>

		<div class="query-chat-scroll" bind:this={scrollEl}>
			{#if turns.length === 0}
				<div class="query-welcome">
					<span class="query-welcome-icon" aria-hidden="true">
						<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.query} /></svg>
					</span>
					<h3>¿Qué quieres investigar?</h3>
					<p>Explora las menciones y abre la evidencia de cada resultado.</p>
					<div class="suggestions" aria-label="Preguntas sugeridas">
						{#if data.suggestions.length > 0}
							<p class="small muted">
								Sugerencias basadas en la síntesis del {data.suggestionDate}
							</p>
							{#each data.suggestions as question (question)}
								<button type="button" onclick={() => applyPrompt(question)}>
									{question}
								</button>
							{/each}
						{:else}
							<p class="small muted">No hay asuntos sintetizados para esta fecha.</p>
						{/if}
					</div>
				</div>
			{:else}
				<div id="query-answer" aria-live="polite">
					{#each turns as turn, i (i)}
						<QueryAnswer
							question={turn.question}
							answer={turn.answer}
							citations={turn.citations}
							error={turn.error}
							pending={pending && i === turns.length - 1}
						/>
					{/each}
				</div>
			{/if}
		</div>

		<form method="POST" class="query-composer" use:enhance={submitEnhance}>
			<label class="sr-only" for="question">Escribe tu pregunta</label>
			<div class="query-composer-field">
				<textarea
					id="question"
					name="question"
					rows="2"
					maxlength="1000"
					required
					placeholder="Pregunta sobre tu monitoreo..."
					bind:value={draft}
					bind:this={questionField}
				></textarea>
				<button class="button primary" type="submit" aria-label="Enviar consulta" disabled={pending}>
					<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.arrow} /></svg>
				</button>
			</div>
			<p>Cada respuesta cita las notas que la sustentan.</p>
		</form>
	</section>

	<aside class="panel aside-panel query-history" aria-labelledby="history-heading">
		<h2 id="history-heading">Historial de preguntas</h2>
		<p class="small muted">El historial se guarda solo en este navegador.</p>
		<!-- Contenedor de items como #query-history-items del mockup: mantiene
		     fuera del alcance de `.query-history > p` (11px) al aviso vacío, que
		     en el mockup mide 12px vía .small. -->
		<div id="query-history-items">
			{#if threads.length === 0}
				<p class="small muted query-history-empty">Aún no hay preguntas guardadas.</p>
			{:else}
				<ol class="query-history-list">
					{#each threads as thread (thread.id)}
						<li>
							<button
								type="button"
								aria-label="Abrir consulta: {threadTitle(thread)}"
								aria-current={thread.id === activeId ? 'true' : undefined}
								onclick={() => (activeId = thread.id)}
							>
								<span>{threadTitle(thread)}</span>
								<time datetime={thread.updatedAt}>{formatDisplayTime(thread.updatedAt)}</time>
							</button>
							<button
								class="delete-chat"
								type="button"
								aria-label="Borrar consulta: {threadTitle(thread)}"
								onclick={() => deleteThread(thread.id)}
							>
								×
							</button>
						</li>
					{/each}
				</ol>
			{/if}
		</div>
		<button class="text-link new-chat" type="button" onclick={startNewChat}>Nueva consulta</button>
	</aside>
</div>

{#if result?.person}
	<p class="footnote">
		Pregunta vinculada a:
		<a href={personDirectoryHref(result.person.name)} class="underline hover:text-ink">
			{result.person.name}
		</a>
	</p>
{/if}
