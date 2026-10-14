import adapter from '@sveltejs/adapter-node';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
	preprocess: vitePreprocess(),
	kit: {
		adapter: adapter(),
		// LAN/Tailscale-only tool: the dashboard is reached via several hosts
		// (localhost, tailnet IP, machine name) and only one ORIGIN env is
		// possible per container, so the default origin check 403s every form
		// POST from any non-canonical host ("Cross-site POST form
		// submissions are forbidden"). Auth surface is the tailnet itself.
		csrf: { checkOrigin: false }
	}
};

export default config;
