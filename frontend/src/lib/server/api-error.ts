import { ApiError } from '$lib/api';

/**
 * Shared cause-mapping for load/action catch blocks: one definition of
 * "which HTTP status and user-facing message a caught cause carries".
 * Loads fall back to 503 (service unavailable); actions to 502.
 */

/** The ApiError's own 4xx/5xx status, else the caller's fallback. */
export function errorStatus(cause: unknown, fallback: number): number {
	return cause instanceof ApiError && cause.status >= 400 ? cause.status : fallback;
}

/** The Error's message when non-empty, else the caller's fallback. */
export function errorMessage(cause: unknown, fallback: string): string {
	return cause instanceof Error && cause.message ? cause.message : fallback;
}
