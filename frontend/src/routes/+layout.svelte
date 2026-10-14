<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	const navItems = [
		{ href: '/', label: 'Feed' },
		{ href: '/events', label: 'Eventos' },
		{ href: '/persons', label: 'Personas' },
		{ href: '/consultas', label: 'Consultas' },
		{ href: '/stats', label: 'Estadísticas' },
		{ href: '/summary', label: 'Resumen' },
		{ href: '/saved-searches', label: 'Saved searches' },
		{ href: '/keywords', label: 'Palabras clave' },
		{ href: '/alerts', label: 'Alertas' },
		{ href: '/settings', label: 'Configuración' }
	];

	let menuOpen = $state(false);

	function isActive(href: string): boolean {
		const path = page.url.pathname;
		return href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`);
	}

	function closeMenu(): void {
		menuOpen = false;
	}
</script>

<div class="flex min-h-screen flex-col">
	<header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
		<div class="mx-auto flex w-full max-w-6xl items-center justify-between gap-x-6 px-4 py-3 sm:px-6">
			<a href="/" class="text-lg font-semibold tracking-tight text-slate-900">Media Monitor</a>

			<!-- Desktop: the historical single row, unchanged. -->
			<nav aria-label="Principal" class="hidden flex-wrap gap-1 md:flex">
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

			<!-- Mobile: hamburger toggling a two-column panel. -->
			<button
				type="button"
				aria-expanded={menuOpen}
				aria-controls="mobile-nav"
				aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
				onclick={() => (menuOpen = !menuOpen)}
				class="flex size-10 items-center justify-center rounded-lg text-slate-600 hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-300 md:hidden"
			>
				{#if menuOpen}
					<svg class="size-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
						<path d="M5 5l10 10M15 5L5 15" stroke-linecap="round" />
					</svg>
				{:else}
					<svg class="size-5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
						<path d="M3 5h14M3 10h14M3 15h14" stroke-linecap="round" />
					</svg>
				{/if}
			</button>
		</div>

		{#if menuOpen}
			<nav
				id="mobile-nav"
				aria-label="Principal móvil"
				class="border-t border-slate-100 bg-white px-4 pb-3 pt-2 shadow-lg md:hidden"
			>
				<ul class="grid grid-cols-2 gap-1">
					{#each navItems as item (item.href)}
						<li>
							<a
								href={item.href}
								aria-current={isActive(item.href) ? 'page' : undefined}
								onclick={closeMenu}
								class={`block rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
									isActive(item.href)
										? 'bg-slate-900 text-white'
										: 'text-slate-700 hover:bg-slate-100'
								}`}
							>
								{item.label}
							</a>
						</li>
					{/each}
				</ul>
			</nav>
		{/if}
	</header>

	<main class="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
		{@render children?.()}
	</main>
</div>
