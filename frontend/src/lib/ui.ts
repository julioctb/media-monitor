/**
 * Single source of truth for form-control skin. Geometry lives in the
 * `--radius-control` token (src/app.css); NO component may hardcode
 * rounded-lg/rounded-full on an input, select or textarea. Colors come
 * from the 'referencia visual' token port in app.css (@theme --color-*).
 *
 * Variants may append layout (w-full, flex-1) and density (px/py/text-*)
 * — never border/radius/shadow/focus.
 */
export const CONTROL_CLS =
	'rounded-(--radius-control) border border-line bg-white text-sm text-ink placeholder:text-muted hover:border-meta focus:border-accent focus:outline-none focus:ring-4 focus:ring-accent/25';

/** Standard block field: full width, 44px touch target. */
export const INPUT_CLS = `${CONTROL_CLS} w-full min-h-[44px] px-3 py-2`;

/** Compact inline control (filter bars): still 44px tall. */
export const COMPACT_CLS = `${CONTROL_CLS} min-h-[44px] px-3 py-1.5 text-xs font-medium text-ink-2`;

/** Primary action (mockup .search-button): accent pill, 44px target. */
export const BTN_PRIMARY_CLS =
	'inline-flex min-h-[44px] items-center justify-center rounded-full border border-accent bg-accent px-[22px] text-sm font-semibold text-accent-on transition-colors hover:border-accent-hover hover:bg-accent-hover active:border-accent-active active:bg-accent-active disabled:opacity-60';

/** Secondary action: neutral pill, 44px target. */
export const BTN_GHOST_CLS =
	'inline-flex min-h-[44px] items-center justify-center rounded-full border border-line bg-white px-[22px] text-sm font-semibold text-ink-2 transition-colors hover:bg-surface-warm disabled:opacity-60';
