import { redirect } from '@sveltejs/kit';
import type { PageServerLoad } from './$types';

/** The digest is home since the reader-first reshuffle; keep old links warm. */
export const load: PageServerLoad = ({ url }) => {
	redirect(301, `/${url.search}`);
};
