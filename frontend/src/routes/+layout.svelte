<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	interface NavGroup {
		label: string;
		href: string;
	}

	// Flat nav, mockup order. Configuración is a single page: its sections
	// (keywords included) are anchors inside /settings, not sub-tabs.
	const navGroups: NavGroup[] = [
		{ label: 'Resumen', href: '/' },
		{ label: 'Feed', href: '/feed' },
		{ label: 'Campo', href: '/campo' },
		{ label: 'Eventos', href: '/events' },
		{ label: 'Agenda', href: '/agenda' },
		{ label: 'Actores', href: '/persons' },
		{ label: 'Consultas', href: '/consultas' },
		{ label: 'Estadísticas', href: '/stats' },
		{ label: 'Búsquedas', href: '/saved-searches' },
		{ label: 'Revisiones', href: '/revisiones' },
		{ label: 'Configuración', href: '/settings' }
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

			<nav class={`nav${menuOpen ? ' open' : ''}`} id="primary-nav" aria-label="Navegación principal">
				{#each navGroups as group (group.href)}
					<a
						href={group.href}
						aria-current={isActive(group.href) ? 'page' : undefined}
						onclick={closeMenu}
					>
						{group.label}
					</a>
				{/each}
			</nav>
		</div>
	</header>

	<main class="page flex-1 w-full">
		{@render children?.()}
	</main>
</div>
