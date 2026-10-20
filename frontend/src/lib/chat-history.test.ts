// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';

import {
	CHAT_STORAGE_KEY,
	MAX_THREADS,
	appendTurn,
	createThread,
	loadThreads,
	saveThreads,
	threadTitle
} from './chat-history';

/** Minimal Storage double (jsdom localStorage also works). */
function memoryStorage(): Storage {
	const map = new Map<string, string>();
	return {
		get length() {
			return map.size;
		},
		clear: () => map.clear(),
		getItem: (key: string) => map.get(key) ?? null,
		key: () => null,
		removeItem: (key: string) => void map.delete(key),
		setItem: (key: string, value: string) => void map.set(key, value)
	};
}

const NOW = new Date('2026-10-19T12:00:00Z');

describe('appendTurn', () => {
	it('adds user + assistant messages with citations', () => {
		const thread = createThread(NOW.toISOString());
		const updated = appendTurn(
			thread,
			{
				question: '¿Qué se publicó sobre becas?',
				answer: 'La BUAP reportó 75 mil becas.',
				citations: [{ mention_id: 1, title: 'Becas', url: 'https://a/1' }]
			},
			NOW
		);
		expect(updated.messages).toHaveLength(2);
		expect(updated.messages[0]).toMatchObject({ role: 'user', text: '¿Qué se publicó sobre becas?' });
		expect(updated.messages[1]?.citations).toHaveLength(1);
		expect(updated.updatedAt).toBe(NOW.toISOString());
		// Pure: the input thread is untouched.
		expect(thread.messages).toHaveLength(0);
	});

	it('records a notice instead of an answer on error', () => {
		const updated = appendTurn(
			createThread(),
			{ question: 'hola', error: 'No se pudo consultar' },
			NOW
		);
		expect(updated.messages.map((message) => message.role)).toEqual(['user', 'notice']);
	});

	it('records only the question when nothing came back', () => {
		const updated = appendTurn(createThread(), { question: 'hola' }, NOW);
		expect(updated.messages.map((message) => message.role)).toEqual(['user']);
	});
});

describe('threadTitle', () => {
	it('uses the first user question, truncated', () => {
		const thread = appendTurn(createThread(), { question: 'x'.repeat(80) }, NOW);
		expect(threadTitle(thread)).toHaveLength(49);
		expect(threadTitle(thread).endsWith('…')).toBe(true);
	});

	it('degrades without user messages', () => {
		expect(threadTitle(createThread())).toBe('Consulta sin preguntas');
	});
});

describe('loadThreads / saveThreads', () => {
	it('roundtrips through storage', () => {
		const storage = memoryStorage();
		const thread = appendTurn(createThread(), { question: '¿Becas?', answer: 'Sí' }, NOW);
		saveThreads(storage, [thread]);
		const loaded = loadThreads(storage);
		expect(loaded).toHaveLength(1);
		expect(loaded[0]?.messages[0]?.text).toBe('¿Becas?');
	});

	it('drops malformed entries instead of throwing', () => {
		const storage = memoryStorage();
		storage.setItem(
			CHAT_STORAGE_KEY,
			JSON.stringify([{ id: 'ok', messages: [] }, { junk: true }, null, 'x'])
		);
		// Missing createdAt/updatedAt → dropped.
		expect(loadThreads(storage)).toHaveLength(0);
	});

	it('returns empty on invalid JSON or missing storage', () => {
		const storage = memoryStorage();
		storage.setItem(CHAT_STORAGE_KEY, '{broken');
		expect(loadThreads(storage)).toEqual([]);
		expect(loadThreads(null)).toEqual([]);
	});

	it('caps the stored thread count', () => {
		const storage = memoryStorage();
		const threads = Array.from({ length: MAX_THREADS + 10 }, () => createThread());
		saveThreads(storage, threads);
		expect(loadThreads(storage)).toHaveLength(MAX_THREADS);
	});
});
