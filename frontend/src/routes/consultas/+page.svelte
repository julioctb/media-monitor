<script lang="ts">
	import type { PageProps, SubmitFunction } from './$types';

	import { browser } from '$app/environment';
	import { enhance } from '$app/forms';

	import {
		appendTurn,
		createThread,
		loadThreads,
		saveThreads,
		threadTitle,
		type ChatThread
	} from '$lib/chat-history';
	import { formatDisplayDateTime, sentimentLabel, sourceLabel } from '$lib/format';

	let { form: result }: PageProps = $props();

	let threads = $state<ChatThread[]>(browser ? loadThreads(localStorage) : []);
	let activeId = $state<string | null>(null);
	let processedTurn = $state(0);
	// The draft lives client-side: cleared on success, kept on error. The
	// server-echoed question (result.question) feeds the history, not the input.
	let draft = $state('');
	let pending = $state(false);

	// Preguntas ejemplo del welcome (mockup queryView div.suggestions): el
	// click rellena el composer y devuelve el foco para editar y enviar.
	const SUGGESTED_QUESTIONS = [
		'¿Qué se reportó hoy sobre seguridad?',
		'¿Qué se publicó esta semana sobre la BUAP?',
		'¿Quién aparece en las notas sobre transporte?'
	];
	let questionField: HTMLTextAreaElement | undefined;

	function applyPrompt(question: string) {
		draft = question;
		questionField?.focus();
	}

	const submitEnhance: SubmitFunction = () => {
		pending = true;
		return async ({ result, update }) => {
			pending = false;
			// Keep our own reset semantics: the effect above persists the turn
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

	function startNewChat() {
		activeId = null;
	}

	function deleteThread(id: string) {
		threads = threads.filter((thread) => thread.id !== id);
		if (activeId === id) activeId = null;
		saveThreads(localStorage, threads);
	}
</script>

<svelte:head>
	<title>Consultas | Media Monitor</title>
</svelte:head>

<header class="intro">
	<h1 class="page-title">Consultas</h1>
	<p class="lead">
		Pregunta en lenguaje natural sobre la cobertura. Las respuestas se apoyan exclusivamente en
		notas ingestadas y muestran sus citas.
	</p>
</header>

<div class="workspace">
	<aside class="panel history" aria-labelledby="history-heading">
		<div class="history-head">
			<h2 id="history-heading">Historial</h2>
			<button class="new-chat" type="button" onclick={startNewChat}>Nuevo chat</button>
		</div>
		{#if threads.length === 0}
			<p class="history-empty">Todavía no hay consultas guardadas.</p>
		{:else}
			<ul class="history-list">
				{#each threads as thread (thread.id)}
					<li class="history-item" class:active={thread.id === activeId}>
						<button
							class="history-open"
							type="button"
							aria-label="Abrir consulta: {threadTitle(thread)}"
							onclick={() => (activeId = thread.id)}
						>
							<span class="history-title">{threadTitle(thread)}</span>
							<span class="history-preview">{formatDisplayDateTime(thread.updatedAt)}</span>
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
			</ul>
		{/if}
		<p class="storage-note">El historial se guarda solo en este navegador.</p>
	</aside>

	<section class="panel chat" aria-labelledby="chat-heading">
		<div class="chat-head">
			<h2 id="chat-heading">{active ? threadTitle(active) : 'Nueva consulta'}</h2>
			<p class="chat-subtitle">
				Las respuestas se generan solo con notas ingestadas y muestran sus citas.
			</p>
		</div>

		<div class="messages" aria-live="polite">
			{#if !active || active.messages.length === 0}
				<div class="welcome">
					<strong>Explora la cobertura</strong>
					Haz una pregunta sobre las notas registradas. La respuesta debe incluir citas
					verificables.
					<div class="suggestions" aria-label="Preguntas sugeridas">
						{#each SUGGESTED_QUESTIONS as question (question)}
							<button type="button" onclick={() => applyPrompt(question)}>{question}</button>
						{/each}
					</div>
				</div>
			{:else}
					{#each active.messages as message, i (`${message.at}-${i}`)}
						<article class="message {message.role}">
							<span class="message-label">
								{message.role === 'user'
									? 'Tu pregunta'
									: message.role === 'assistant'
										? 'Respuesta con citas'
										: 'Estado de la consulta'}
							</span>
							<p>{message.text}</p>
							{#if message.role === 'assistant' && message.citations && message.citations.length > 0}
								<ol class="citations">
									{#each message.citations as citation (citation.mention_id)}
										<li>
											<a href={citation.url} target="_blank" rel="noopener noreferrer">
												{citation.title ?? citation.url}
											</a>
											{#if citation.source}
												<span class="citation-meta">
													{sourceLabel(citation.source)} ·
													{formatDisplayDateTime(citation.published_at)}{#if citation.sentiment}
														· {sentimentLabel(citation.sentiment)}{/if}
												</span>
											{/if}
										</li>
									{/each}
								</ol>
							{/if}
						</article>
					{/each}
			{/if}
		</div>

		<form method="POST" class="composer" use:enhance={submitEnhance}>
			<label for="question">Tu pregunta</label>
			<textarea
				id="question"
				name="question"
				maxlength="1000"
				required
				bind:value={draft}
				bind:this={questionField}
				placeholder="Por ejemplo: ¿Qué se publicó sobre la BUAP esta semana?"
			></textarea>
			<div class="composer-actions">
				<p class="composer-note">Cada respuesta cita las notas que la sustentan.</p>
				<button class="send" type="submit" disabled={pending}>
					{pending ? 'Consultando…' : 'Enviar pregunta'}
				</button>
			</div>
		</form>
	</section>
</div>

{#if result?.person}
	<p class="footnote">
		Pregunta vinculada a:
		<a href={`/persons/${result.person.id}`} class="underline hover:text-ink">
			{result.person.name}
		</a>
	</p>
{/if}
