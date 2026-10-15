/**
 * Single source of truth for form-control skin. Geometry lives in the
 * `--radius-control` token (src/app.css); NO component may hardcode
 * rounded-lg/rounded-full on an input, select or textarea.
 *
 * Variants may append layout (w-full, flex-1) and density (px/py/text-*)
 * — never border/radius/shadow/focus.
 */
export const CONTROL_CLS =
	'rounded-(--radius-control) border border-slate-300 bg-white text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-slate-500 focus:outline-none focus:ring-2 focus:ring-slate-200';

/** Standard block field: full width, comfortable padding. */
export const INPUT_CLS = `${CONTROL_CLS} w-full px-3 py-2`;

/** Compact inline control (filter bars): chip-height. */
export const COMPACT_CLS = `${CONTROL_CLS} px-3 py-1.5 text-xs font-medium text-slate-700`;
