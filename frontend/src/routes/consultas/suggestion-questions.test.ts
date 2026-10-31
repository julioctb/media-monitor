import { describe, expect, it } from 'vitest';

import { suggestionQuestions } from '$lib/format';

type News = { title: string | null; topic?: string | null };

const news = (topic: string | null, title: string | null = 'Nota |'): News =>
	({ title, topic }) as News;

describe('suggestionQuestions', () => {
	it('builds the mockup question from the canonical topic', () => {
		expect(suggestionQuestions([news('Mesa de Movilidad')])).toEqual([
			'¿Qué se reportó sobre mesa de Movilidad?'
		]);
	});

	it('dedupes repeated topics: the digest may cover one topic twice', () => {
		const items = [
			news('Academia'),
			news('Academia'),
			news('Agua'),
			news('Academia'),
			news('Nómina')
		];
		const out = suggestionQuestions(items);
		expect(new Set(out).size).toBe(out.length);
		expect(out).toEqual([
			'¿Qué se reportó sobre academia?',
			'¿Qué se reportó sobre agua?',
			'¿Qué se reportó sobre nómina?'
		]);
	});

	it('keeps the first three distinct questions', () => {
		const items = [news('A'), news('A'), news('B'), news('C'), news('D')];
		expect(suggestionQuestions(items)).toEqual([
			'¿Qué se reportó sobre a?',
			'¿Qué se reportó sobre b?',
			'¿Qué se reportó sobre c?'
		]);
	});

	it('dedupes by headline too when no topic exists', () => {
		const items = [news(null, 'Misma nota |'), news(null, 'Misma nota |')];
		expect(suggestionQuestions(items)).toEqual(['¿Qué se reportó sobre misma nota?']);
	});

	it('returns nothing for an empty digest', () => {
		expect(suggestionQuestions([])).toEqual([]);
	});
});
