/**
 * Single global toast (mockup #toast): one message at a time, fixed copy,
 * 3500 ms lifetime. The outlet lives in the root layout (Toaster.svelte);
 * any component reports through `notify` / `notifyPersist`.
 */
const TOAST_MS = 3500;

let timer: ReturnType<typeof setTimeout> | undefined;

export const toast = $state({ message: null as string | null });

/** Persistence copy, verbatim from the mockup toggle() flow. */
export const TOAST_PERSISTED = 'Preferencia guardada en este navegador.';
export const TOAST_SESSION_FALLBACK =
	'Cambio aplicado durante esta sesión. El navegador no permite guardarlo.';

export function notify(message: string): void {
	toast.message = message;
	if (timer) clearTimeout(timer);
	timer = setTimeout(() => {
		toast.message = null;
	}, TOAST_MS);
}

/** Toast the result of a preference write (success copy or session fallback). */
export function notifyPersist(persisted: boolean): void {
	notify(persisted ? TOAST_PERSISTED : TOAST_SESSION_FALLBACK);
}
