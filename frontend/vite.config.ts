import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vitest/config';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	// Vitest only (guarded so `vite build` keeps its own conditions): the
	// `browser` export condition makes `svelte` resolve to index-client.js
	// (mount) instead of the server build in component tests.
	...(process.env.VITEST === 'true' ? { resolve: { conditions: ['browser'] } } : {}),
	test: {
		include: ['src/**/*.test.ts'],
		environment: 'node'
	}
});
