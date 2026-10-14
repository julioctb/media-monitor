<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	interface NavNode {
		href: string;
		label: string;
	}

	interface NavGroup {
		/** Nav label; grouped entries link to their primary child. */
		label: string;
		href: string;
		/** Present = grouped section: children render as the sub-tab strip. */
		children?: NavNode[];
	}

	// Grouped by intent (informarse / analizar / vigilar / configurar). Routes
	// are untouched: groups only change navigation, so saved links keep
	// working. A group's second page is reached via the tab strip, never a
	// JS dropdown.
	const navGroups: NavGroup[] = [
		{ label: 'Feed', href: '/' },
		{ label: 'Eventos', href: '/events' },
		{ label: 'Personas', href: '/persons' },
		{ label: 'Consultas', href: '/consultas' },
		{
			label: 'Análisis',
			href: '/stats',
			children: [
				{ href: '/stats', label: 'Estadísticas' },
				{ href: '/summary', label: 'Resumen diario' }
			]
		},
		{
			label: 'Alertas',
			href: '/alerts',
			children: [
				{ href: '/alerts', label: 'Alertas' },
				{ href: '/saved-searches', label: 'Búsquedas guardadas' }
			]
		},
		{
			label: 'Configuración',
			href: '/settings',
			children: [
				{ href: '/settings', label: 'General' },
				{ href: '/keywords', label: 'Palabras clave' }
			]
		}
	];

	let menuOpen = $state(false);
	const tabs = $derived(activeTabs());

	function isActive(href: string): boolean {
		const path = page.url.pathname;
		return href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`);
	}

	function groupActive(group: NavGroup): boolean {
		return isActive(group.href) || (group.children ?? []).some((child) => isActive(child.href));
	}

	function activeTabs(): NavNode[] | null {
		for (const group of navGroups) {
			if (group.children && groupActive(group)) return group.children;
		}
		return null;
	}

	function closeMenu(): void {
		menuOpen = false;
	}
</script>

<div class="flex min-h-screen flex-col">
	<header class="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
		<div class="mx-auto flex w-full max-w-6xl items-center justify-between gap-x-6 px-4 py-3 sm:px-6">
			<a href="/" class="text-lg font-semibold tracking-tight text-slate-900">Media Monitor</a>

			<!-- Desktop: one entry per group; sub-pages live in the tab strip. -->
			<nav aria-label="Principal" class="hidden flex-wrap gap-1 md:flex">
				{#each navGroups as group (group.label)}
					<a
						href={group.href}
						aria-current={groupActive(group) ? 'page' : undefined}
						class={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
							groupActive(group)
								? 'bg-slate-900 text-white'
								: 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
						}`}
					>
						{group.label}
					</a>
				{/each}
			</nav>

			<!-- Mobile: hamburger toggling grouped sections. -->
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
				<ul class="grid gap-1 sm:grid-cols-2">
					{#each navGroups as group (group.label)}
						<li>
							{#if group.children}
								<p class="px-3 pb-1 pt-2 text-2xs font-semibold uppercase tracking-wider text-slate-400">
									{group.label}
								</p>
								<ul>
									{#each group.children as child (child.href)}
										<li>
											<a
												href={child.href}
												aria-current={isActive(child.href) ? 'page' : undefined}
												onclick={closeMenu}
												class={`block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
													isActive(child.href)
														? 'bg-slate-900 text-white'
														: 'pl-5 text-slate-700 hover:bg-slate-100'
												}`}
											>
												{child.label}
											</a>
										</li>
									{/each}
								</ul>
							{:else}
								<a
									href={group.href}
									aria-current={isActive(group.href) ? 'page' : undefined}
									onclick={closeMenu}
									class={`mt-1 block rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
										isActive(group.href)
											? 'bg-slate-900 text-white'
											: 'text-slate-700 hover:bg-slate-100'
									}`}
								>
									{group.label}
								</a>
							{/if}
						</li>
					{/each}
				</ul>
			</nav>
		{/if}

		{#if tabs && !menuOpen}
			<!-- Sub-navigation for the active group, every breakpoint. -->
			<nav aria-label="Sección" class="border-t border-slate-100 bg-white">
				<div class="mx-auto flex w-full max-w-6xl gap-1 px-4 py-1.5 sm:px-6">
					{#each tabs as tab (tab.href)}
						<a
							href={tab.href}
							aria-current={isActive(tab.href) ? 'page' : undefined}
							class={`rounded-full px-3 py-1 text-xs font-medium transition-colors ${
								isActive(tab.href)
									? 'bg-slate-900 text-white'
									: 'text-slate-500 hover:bg-slate-100 hover:text-slate-900'
							}`}
						>
							{tab.label}
						</a>
					{/each}
				</div>
			</nav>
		{/if}
	</header>

	<main class="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
		{@render children?.()}
	</main>
</div>
