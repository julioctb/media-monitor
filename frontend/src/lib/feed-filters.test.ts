import { describe, expect, it } from 'vitest';

import { channelSources, dateRangeError, isFeedChannel, splitSources } from './feed-filters';

describe('splitSources', () => {
	it('puts news sources first and leaves the rest as social', () => {
		const { news, social } = splitSources(['x_twitter', 'news_rss', 'gdelt', 'facebook_page']);
		expect(news).toEqual(['news_rss', 'gdelt']);
		expect(social).toEqual(['x_twitter', 'facebook_page']);
	});
});

describe('channelSources', () => {
	const groups = { news: ['news_rss'], social: ['x_twitter'] };

	it('maps each channel to its source set', () => {
		expect(channelSources('', groups)).toEqual([]);
		expect(channelSources('news', groups)).toEqual(['news_rss']);
		expect(channelSources('social', groups)).toEqual(['x_twitter']);
	});

	it('field has no ingest sources yet', () => {
		expect(channelSources('field', groups)).toEqual([]);
	});
});

describe('isFeedChannel', () => {
	it('accepts the four channel values only', () => {
		for (const value of ['', 'news', 'social', 'field']) expect(isFeedChannel(value)).toBe(true);
		expect(isFeedChannel('everything')).toBe(false);
		expect(isFeedChannel(null)).toBe(false);
	});
});

describe('dateRangeError', () => {
	it('passes when a bound is missing', () => {
		expect(dateRangeError('', '2026-10-01')).toBeNull();
		expect(dateRangeError('2026-10-01', '')).toBeNull();
	});

	it('flags inverted ranges', () => {
		expect(dateRangeError('2026-10-02', '2026-10-01')).toBe(
			'La fecha inicial no puede ser posterior a la fecha final.'
		);
		expect(dateRangeError('2026-10-01', '2026-10-02')).toBeNull();
		expect(dateRangeError('2026-10-01', '2026-10-01')).toBeNull();
	});
});
