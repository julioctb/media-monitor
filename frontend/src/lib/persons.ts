import type { PersonTimelineItem } from '$lib/api';
import { displayDayKey } from '$lib/format';

/** Directory preferences and visible counts are local to this bounded pool. */
export const PERSONS_DIRECTORY_LIMIT = 200;
export const PERSONS_PAGE_SIZE = 25;
export const PERSON_TIMELINE_PAGE_SIZE = 25;

export function personDirectoryHref(name: string): string {
	const params = new URLSearchParams({ q: name });
	return `/persons?${params.toString()}`;
}

export interface PersonTimelineGroup {
	key: string;
	items: PersonTimelineItem[];
}

export function groupPersonTimeline(items: PersonTimelineItem[]): PersonTimelineGroup[] {
	const groups: PersonTimelineGroup[] = [];
	const indexes = new Map<string, number>();
	for (const item of items) {
		const key = displayDayKey(item.published_at ?? item.ingested_at);
		const index = indexes.get(key);
		if (index === undefined) {
			indexes.set(key, groups.length);
			groups.push({ key, items: [item] });
		} else {
			groups[index].items.push(item);
		}
	}
	return groups;
}

interface TimelineMetadata {
	timeline: PersonTimelineItem[];
	timeline_total?: number;
	timeline_limit?: number;
	timeline_offset?: number;
}

export function personTimelinePage(
	person: TimelineMetadata,
	request: { limit: number; offset: number }
) {
	const limit = person.timeline_limit ?? request.limit;
	const offset = person.timeline_offset ?? request.offset;
	const total = person.timeline_total ?? null;
	return {
		limit,
		offset,
		total,
		hasPrevious: offset > 0,
		hasNext: total === null ? person.timeline.length >= limit : offset + person.timeline.length < total
	};
}
