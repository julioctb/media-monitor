/**
 * Single source of icon paths (v3 mockup app.js `paths`, verbatim).
 * Render as: <svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true">
 * <path d={ICON_PATHS[name]} /></svg>
 */
export const ICON_PATHS = {
	feed: 'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h5',
	events:
		'M5 5h5v5H5z M14 5h5v5h-5z M5 14h5v5H5z M14 14h5v5h-5z',
	agenda: 'M5 5h14v15H5z M8 3v4 M16 3v4 M5 10h14 M9 14h2',
	people:
		'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M20 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
	query: 'M4 4h16v13H9l-5 4z M8 8h8 M8 12h5',
	settings:
		'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
	search: 'M20 20l-5-5 M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14',
	arrow: 'M5 12h14 M13 6l6 6-6 6',
	chevron: 'm9 5 7 7-7 7',
	bookmark: 'M6 3h12v18l-6-4-6 4z',
	social:
		'M5 14a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M19 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M19 22a3 3 0 1 0 0-6 3 3 0 0 0 0 6 M8 10l8-4 M8 12l8 6',
	field: 'm21 3-7 18-4-7-7-4 18-7z M10 14 21 3',
	clock: 'M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20 M12 6v6l4 2',
	link: 'M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-2 2 M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l2-2',
	close: 'M6 6l12 12 M6 18 18 6',
	menu: 'M4 6h16 M4 12h16 M4 18h16',
	check: 'm5 12 4 4L19 6',
	download: 'M12 3v12 M7 10l5 5 5-5 M4 16v5h16v-5',
	layers: 'm12 3 10 6-10 6L2 9l10-6z M2 14l10 6 10-6',
	stats: 'M5 20V10 M12 20V4 M19 20v-8'
} as const;

export type IconName = keyof typeof ICON_PATHS;

/** Path for an icon; unknown names fall back to the feed glyph (mockup `paths[n]||paths.feed`). */
export function iconPath(name: string): string {
	return (ICON_PATHS as Record<string, string>)[name] ?? ICON_PATHS.feed;
}
