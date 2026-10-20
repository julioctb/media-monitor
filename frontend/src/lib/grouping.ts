import type { Mention } from './api';

/** A feed render group: one canonical event's coverage, or a lone mention. */
export interface FeedGroup {
	/** Stable key: `event:<id>` or `single:<mentionId>`. */
	key: string;
	/** Canonical event when the group spans 2+ mentions. */
	event: { id: number; title: string } | null;
	/** Group members, feed order preserved (representative first). */
	mentions: Mention[];
}

/**
 * Collapse mentions that belong to the same canonical event so the feed shows
 * one card per story. Groups keep first-appearance order; members keep the
 * incoming sort inside the group. Single-mention "events" render plain, so
 * grouping is invisible until coverage is actually duplicated.
 */
export function groupByEvent(mentions: Mention[]): FeedGroup[] {
	const groups: FeedGroup[] = [];
	byEvent: for (const mention of mentions) {
		const eventId = mention.event_id ?? null;
		if (eventId == null) {
			groups.push({ key: `single:${mention.id}`, event: null, mentions: [mention] });
			continue;
		}
		for (const group of groups) {
			if (group.event?.id === eventId) {
				group.mentions.push(mention);
				continue byEvent;
			}
		}
		// First sight of this event: it may still be a singleton.
		groups.push({
			key: `event:${eventId}`,
			event: {
				id: eventId,
				title: mention.event_title ?? `Evento ${eventId}`
			},
			mentions: [mention]
		});
	}
	// Promote singleton event groups to plain mentions on render; keep them
	// here so the group count matches the event reality, and let the component
	// decide presentation (extra members = expandable).
	return groups;
}
