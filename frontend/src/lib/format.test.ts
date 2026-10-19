import { describe, expect, it } from 'vitest';
import { eventChipLabel, classificationLabel } from './format';

describe('eventChipLabel', () => {
	it('returns a plain CTA when the event title near-duplicates the mention title', () => {
		const title = 'Pone en marcha la rectora Lilia Cedillo campaña Échale los kilos';
		const event = 'Pone en marcha Rectora de la BUAP, Lilia Cedillo, campaña “Échale los kilos” - Boletines BUAP';
		expect(eventChipLabel(title, event)).toBe('Ver evento');
	});

	it('keeps the event title when it adds real information', () => {
		expect(
			eventChipLabel(
				'BUAP inaugura laboratorio de robotics',
				'Rectoría presenta el nuevo plan de becas 2027'
			)
		).toBe('Evento: Rectoría presenta el nuevo plan de becas 2027');
	});

	it('degrades to the full label on empty inputs', () => {
		expect(eventChipLabel(null, 'Evento X')).toBe('Evento: Evento X');
		expect(eventChipLabel('Título', '')).toBe('Evento: ');
	});
});

describe('classificationLabel', () => {
	it('maps the full political enum, uncertain included', () => {
		expect(classificationLabel('political')).toBe('Política');
		expect(classificationLabel('not_political')).toBe('No política');
		expect(classificationLabel('uncertain')).toBe('Sin clasificar');
	});

	it('passes unknown labels through untouched', () => {
		expect(classificationLabel('whatever')).toBe('whatever');
	});
});
