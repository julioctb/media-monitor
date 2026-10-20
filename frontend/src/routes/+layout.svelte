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

	// Flat nav, mockup order. Estadísticas/Alertas are real pages and stay;
	// Alertas/Configuración keep a sub-tab strip for their secondary pages
	// (saved-searches / keywords) instead of more top-level entries.
	const navGroups: NavGroup[] = [
		{ label: 'Resumen', href: '/' },
		{ label: 'Feed', href: '/feed' },
		{ label: 'Eventos', href: '/events' },
		{ label: 'Actores', href: '/persons' },
		{ label: 'Consultas', href: '/consultas' },
		{ label: 'Estadísticas', href: '/stats' },
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
	<header class="topbar">
		<div class="topbar-inner">
			<a href="/" class="brand">Media Monitor</a>

			<button
				type="button"
				class="menu-toggle"
				aria-expanded={menuOpen}
				aria-controls="primary-nav"
				aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
				onclick={() => (menuOpen = !menuOpen)}
			>
				{menuOpen ? 'Cerrar' : 'Menú'}
			</button>

			<nav class={`nav${menuOpen ? ' open' : ''}`} id="primary-nav" aria-label="Principal">
				{#each navGroups as group (group.href)}
					<a
						href={group.href}
						aria-current={groupActive(group) ? 'page' : undefined}
						onclick={closeMenu}
					>
						{group.label}
					</a>
				{/each}
			</nav>
		</div>

		{#if tabs && !menuOpen}
			<!-- Sub-navigation for the active group, every breakpoint. -->
			<nav aria-label="Sección" class="subnav">
				<div class="subnav-inner">
					{#each tabs as tab (tab.href)}
						<a href={tab.href} aria-current={isActive(tab.href) ? 'page' : undefined}>
							{tab.label}
						</a>
					{/each}
				</div>
			</nav>
		{/if}
	</header>

	<main class="page flex-1">
		{@render children?.()}
	</main>
</div>
