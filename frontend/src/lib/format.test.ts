import { describe, expect, it } from 'vitest';
import {
	eventChipLabel,
	classificationLabel,
	formatLongDate,
	zonedDayBounds
} from './format';

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

describe('formatLongDate', () => {
	it('renders the mockup wording for a known date', () => {
		expect(formatLongDate('2026-10-19')).toBe('Lunes 19 de octubre, 2026');
	});

	it('capitalizes the weekday and handles month boundaries', () => {
		expect(formatLongDate('2026-01-01')).toBe('Jueves 1 de enero, 2026');
	});

	it('falls through for non-ISO input', () => {
		expect(formatLongDate('19/10/2026')).toBe('19/10/2026');
	});
});

describe('zonedDayBounds', () => {
	it('bounds the day in Mexico City (-06:00, no DST)', () => {
		expect(zonedDayBounds('2026-10-22')).toEqual({
			since: '2026-10-22T00:00:00-06:00',
			until: '2026-10-22T23:59:59-06:00'
		});
	});

	it('samples the offset per date, DST zones included', () => {
		expect(zonedDayBounds('2026-01-15', 'America/New_York').since).toBe(
			'2026-01-15T00:00:00-05:00'
		);
		expect(zonedDayBounds('2026-07-15', 'America/New_York').since).toBe(
			'2026-07-15T00:00:00-04:00'
		);
	});
});
