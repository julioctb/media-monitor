import { writable } from 'svelte/store';

/**
 * User preferences — saved news, followed events and seen markers (the v3
 * mockup's `mine-demo-v1` localStorage, ported to ONE cookie so the SERVER
 * LOADS can see it: the feed focus panel and the event buttons render from
 * `data`, and localStorage is invisible to `+page.server.ts`).
 *
 * Substrate: cookie `mm_prefs` = JSON `{saved:[],follow:[],seen:{}}`,
 * `path=/`, `SameSite=Lax`. The client writes it on every toggle (instant,
 * no round trip); server loads read it through the SvelteKit `cookies`
 * helper with tolerant parsing — a malformed cookie degrades to the empty
 * prefs, never an error. The store is seeded from the load data at page
 * init, so the first paint already carries the cookie state.
 */

export const MM_PREFS_COOKIE = 'mm_prefs';

/** Persistent like the mockup's localStorage: one year. */
const MM_PREFS_MAX_AGE = 60 * 60 * 24 * 365;

export interface MmPrefs {
	/** Saved mention ids (botón «Guardar noticia»). */
	saved: number[];
	/** Followed event ids («Seguir evento»). */
	follow: number[];
	/** event id -> last seen marker (the event's `last_seen_at`). */
	seen: Record<string, string>;
}

function emptyPrefs(): MmPrefs {
	return { saved: [], follow: [], seen: {} };
}

const asIdList = (value: unknown): number[] =>
	Array.isArray(value) ? value.filter((id): id is number => Number.isInteger(id)) : [];

/** Tolerant parse: anything malformed degrades to the empty prefs. */
export function parsePrefs(raw: string | null | undefined): MmPrefs {
	if (!raw) return emptyPrefs();
	try {
		const parsed: unknown = JSON.parse(raw);
		if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return emptyPrefs();
		const record = parsed as Record<string, unknown>;
		const seenRaw = record.seen;
		const seen =
			seenRaw && typeof seenRaw === 'object' && !Array.isArray(seenRaw)
				? Object.fromEntries(
						Object.entries(seenRaw as Record<string, unknown>)
							.filter((entry): entry is [string, string] => typeof entry[1] === 'string')
					)
				: {};
		return { saved: asIdList(record.saved), follow: asIdList(record.follow), seen };
	} catch {
		return emptyPrefs();
	}
}

export function serializePrefs(prefs: MmPrefs): string {
	return JSON.stringify({ saved: prefs.saved, follow: prefs.follow, seen: prefs.seen });
}

const prefsStore = writable<MmPrefs>(emptyPrefs());

/** Read-only view for components; seeded from the page data at init. */
export const prefs = { subscribe: prefsStore.subscribe };

let snapshot: MmPrefs = emptyPrefs();
prefsStore.subscribe((value) => {
	snapshot = value;
});

/** Replace the store from server-load data (page init). */
export function seedPrefsFromServer(next: MmPrefs): void {
	prefsStore.set({ saved: [...next.saved], follow: [...next.follow], seen: { ...next.seen } });
}

function persist(next: MmPrefs): boolean {
	if (typeof document === 'undefined') return false;
	try {
		document.cookie = `${MM_PREFS_COOKIE}=${encodeURIComponent(serializePrefs(next))}; path=/; max-age=${MM_PREFS_MAX_AGE}; samesite=lax`;
		return true;
	} catch {
		return false;
	}
}

/** Seen markers only exist while the event is followed (mockup toggle cleanup). */
function pruneSeen(next: MmPrefs): void {
	const followed = new Set(next.follow);
	for (const id of Object.keys(next.seen)) {
		if (!followed.has(Number(id))) delete next.seen[id];
	}
}

function commit(next: MmPrefs): boolean {
	pruneSeen(next);
	const ok = persist(next);
	prefsStore.set(next);
	return ok;
}

/** Toggle one saved mention; returns whether the cookie write persisted. */
export function toggleSaved(id: number): boolean {
	const saved = snapshot.saved.includes(id)
		? snapshot.saved.filter((savedId) => savedId !== id)
		: [...snapshot.saved, id];
	return commit({ ...snapshot, saved, seen: { ...snapshot.seen } });
}

/**
 * Follow/unfollow one event. Following seeds its seen marker with the
 * event's current `last_seen_at` (mockup: seenEvents versioned on follow).
 */
export function setFollow(id: number, follow: boolean, lastSeenAt: string | null): boolean {
	const nextFollow = follow
		? snapshot.follow.includes(id)
			? snapshot.follow
			: [...snapshot.follow, id]
		: snapshot.follow.filter((followed) => followed !== id);
	const seen = { ...snapshot.seen };
	if (follow) {
		if (lastSeenAt) seen[String(id)] = lastSeenAt;
	} else {
		delete seen[String(id)];
	}
	return commit({ ...snapshot, follow: nextFollow, seen });
}

/** Mark a followed event seen up to `lastSeenAt` (mockup eventDetail). */
export function markSeen(id: number, lastSeenAt: string): boolean {
	if (!snapshot.follow.includes(id)) return false;
	return commit({ ...snapshot, seen: { ...snapshot.seen, [String(id)]: lastSeenAt } });
}
