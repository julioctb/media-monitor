/**
 * Local consultation history for the Consultas page.
 *
 * Threads live only in the browser's localStorage (no backend table): the
 * module is pure except for the injected `Storage`, so vitest can exercise
 * the serialization and sanitizing rules.
 */

export interface ChatCitation {
	mention_id: number;
	title: string | null;
	url: string;
	/** Extra provenance fields from the ask endpoint, when present. */
	source?: string;
	published_at?: string | null;
	sentiment?: string | null;
}

export interface ChatMessage {
	role: 'user' | 'assistant' | 'notice';
	text: string;
	/** ISO datetime of the turn. */
	at: string;
	citations?: ChatCitation[];
}

export interface ChatThread {
	id: string;
	title: string | null;
	createdAt: string;
	updatedAt: string;
	messages: ChatMessage[];
}

export const CHAT_STORAGE_KEY = 'media-monitor-consultas-v1';

/** Hard cap so a long session cannot grow the storage unbounded. */
export const MAX_THREADS = 100;

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === 'object' && value !== null;
}

function isThread(value: unknown): value is ChatThread {
	if (!isRecord(value)) return false;
	if (typeof value.id !== 'string') return false;
	if (typeof value.createdAt !== 'string' || typeof value.updatedAt !== 'string') return false;
	if (!Array.isArray(value.messages)) return false;
	return value.messages.every(
		(message) =>
			isRecord(message) &&
			typeof message.text === 'string' &&
			(message.role === 'user' || message.role === 'assistant' || message.role === 'notice')
	);
}

/** Reads threads, dropping malformed entries instead of throwing. */
export function loadThreads(storage: Storage | null | undefined): ChatThread[] {
	if (!storage) return [];
	try {
		const parsed: unknown = JSON.parse(storage.getItem(CHAT_STORAGE_KEY) ?? '[]');
		if (!Array.isArray(parsed)) return [];
		return parsed.filter(isThread).slice(0, MAX_THREADS);
	} catch {
		return [];
	}
}

/** Best-effort persist; quota errors must never break the UI. */
export function saveThreads(storage: Storage | null | undefined, threads: ChatThread[]): void {
	if (!storage) return;
	try {
		storage.setItem(CHAT_STORAGE_KEY, JSON.stringify(threads.slice(0, MAX_THREADS)));
	} catch {
		// Storage full or blocked: keep the in-memory copy only.
	}
}

export function newThreadId(): string {
	const env = globalThis as { crypto?: { randomUUID?: () => string } };
	return env.crypto?.randomUUID?.() ?? `chat-${Date.now()}`;
}

export function createThread(now = new Date().toISOString()): ChatThread {
	return { id: newThreadId(), title: null, createdAt: now, updatedAt: now, messages: [] };
}

/** Visible title: first user question, trimmed for the sidebar. */
export function threadTitle(thread: ChatThread): string {
	const first = thread.messages.find((message) => message.role === 'user');
	if (!first) return 'Consulta sin preguntas';
	return first.text.length > 48 ? `${first.text.slice(0, 48)}…` : first.text;
}

export interface TurnResult {
	question: string;
	answer?: string | null;
	citations?: ChatCitation[] | null;
	error?: string | null;
}

/** Pure reducer: append one Q/A (or error notice) turn to a copy. */
export function appendTurn(thread: ChatThread, result: TurnResult, now = new Date()): ChatThread {
	const at = now.toISOString();
	const messages: ChatMessage[] = [
		...thread.messages,
		{ role: 'user', text: result.question, at }
	];
	if (result.answer) {
		messages.push({
			role: 'assistant',
			text: result.answer,
			at,
			citations: Array.isArray(result.citations) ? result.citations : []
		});
	} else if (result.error) {
		messages.push({ role: 'notice', text: result.error, at });
	}
	return { ...thread, messages, updatedAt: at };
}
