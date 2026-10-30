import { describe, expect, it } from 'vitest';

import {
	MM_PREFS_COOKIE,
	parsePrefs,
	prefs,
	seedPrefsFromServer,
	serializePrefs,
	setFollow,
	setFollowPerson
} from './prefs';

/**
 * mm_prefs carries three ID domains: saved mentions, followed EVENTS and
 * followed PERSONS. The `persons` key must never share `follow` — person
 * ids and event ids collide numerically.
 */

function get(): { saved: number[]; follow: number[]; persons: number[]; seen: Record<string, string> } {
	let value: unknown;
	const unsub = prefs.subscribe((v) => (value = v));
	unsub();
	return value as never;
}

describe('mm_prefs persons key', () => {
	it('defaults persons to an empty list and degrades malformed input', () => {
		expect(parsePrefs(null).persons).toEqual([]);
		expect(parsePrefs('{"persons":"nope"}').persons).toEqual([]);
		expect(parsePrefs('{"persons":[1,"x",3]}').persons).toEqual([1, 3]);
	});

	it('round-trips persons through serialize/parse', () => {
		const parsed = parsePrefs(serializePrefs({ saved: [], follow: [7], persons: [4, 9], seen: {} }));
		expect(parsed.persons).toEqual([4, 9]);
		expect(parsed.follow).toEqual([7]);
	});

	it('setFollowPerson toggles persons without touching event follow/seen', () => {
		seedPrefsFromServer(parsePrefs(`{"saved":[],"follow":[7],"persons":[],"seen":{"7":"t"}}`));
		setFollowPerson(4, true);
		expect(get().persons).toEqual([4]);
		expect(get().follow).toEqual([7]);
		expect(get().seen).toEqual({ '7': 't' });
		// A person id equal to a followed event id does not unfollow the event.
		setFollowPerson(7, true);
		setFollowPerson(7, false);
		expect(get().follow).toEqual([7]);
		expect(get().persons).toEqual([4]);
		setFollowPerson(4, false);
		expect(get().persons).toEqual([]);
	});
});

describe('cookie name stays stable', () => {
	it('is mm_prefs', () => {
		expect(MM_PREFS_COOKIE).toBe('mm_prefs');
	});
});

// setFollow kept here guards the seen-prune contract the persons key must not break.
describe('event follow seen prune still owns seen', () => {
	it('unfollowing an event clears only its seen marker', () => {
		seedPrefsFromServer(parsePrefs('{"saved":[],"follow":[7],"persons":[9],"seen":{"7":"t"}}'));
		setFollow(7, false, null);
		expect(get().seen).toEqual({});
		expect(get().persons).toEqual([9]);
	});
});
