<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const navItems = [
		{ href: '/', label: 'Feed' },
		{ href: '/stats', label: 'Estadísticas' },
		{ href: '/summary', label: 'Resumen' },
		{ href: '/saved-searches', label: 'Saved searches' },
		{ href: '/keywords', label: 'Palabras clave' },
		{ href: '/alerts', label: 'Alertas' },
		{ href: '/settings', label: 'Configuración' }
	];

	function isActive(href: string): boolean {
		const path = page.url.pathname;
		return href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`);
	}
</script>

<div class="flex min-h-screen flex-col">
	<header class="border-b border-slate-200 bg-white">
		<div class="mx-auto flex w-full max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6">
			<a href="/" class="text-lg font-semibold tracking-tight text-slate-900">Media Monitor</a>
			<nav aria-label="Principal" class="flex flex-wrap gap-1">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						aria-current={isActive(item.href) ? 'page' : undefined}
						class={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
							isActive(item.href)
								? 'bg-slate-900 text-white'
								: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
						}`}
					>
						{item.label}
					</a>
				{/each}
			</nav>
		</div>
	</header>

	<main class="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
		{@render children?.()}
	</main>
</div>
