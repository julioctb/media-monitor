<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import pkg from '../../package.json';
	import type { LayoutProps } from './$types';
	import type { SubmitFunction } from './consultas/$types';

	let { children }: LayoutProps = $props();

	const APP_VERSION: string = pkg.version;

	interface NavItem {
		label: string;
		href: string;
		icon: keyof typeof ICONS;
	}

	// Icon paths from the v3 mockup (app.js `paths` map); `stats` added in the
	// same 24px stroke language for the three routes the mockup lacks.
	const ICONS = {
		layers: 'm12 3 10 6-10 6L2 9l10-6z M2 14l10 6 10-6',
		feed: 'M4 4h16v16H4z M8 8h8 M8 12h8 M8 16h5',
		field: 'm21 3-7 18-4-7-7-4 18-7z M10 14 21 3',
		events: 'M5 5h5v5H5z M14 5h5v5h-5z M5 14h5v5H5z M14 14h5v5h-5z',
		agenda: 'M5 5h14v15H5z M8 3v4 M16 3v4 M5 10h14 M9 14h2',
		people: 'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8 M20 21v-2a4 4 0 0 0-3-3.87 M16 3.13a4 4 0 0 1 0 7.75',
		query: 'M4 4h16v13H9l-5 4z M8 8h8 M8 12h5',
		settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M12 2v3 M12 19v3 M2 12h3 M19 12h3 M5 5l2 2 M17 17l2 2 M5 19l2-2 M17 7l2-2',
		stats: 'M5 20V10 M12 20V4 M19 20v-8',
		search: 'M20 20l-5-5 M10 17a7 7 0 1 0 0-14 7 7 0 0 0 0 14',
		arrow: 'M5 12h14 M13 6l6 6-6 6',
		check: 'm5 12 4 4L19 6',
		close: 'M6 6l12 12 M6 18 18 6',
		menu: 'M4 6h16 M4 12h16 M4 18h16'
	};

	// Same routes and copy as the previous topbar; the v3 mockup govern the
	// shell look, not the nav set (11 entries > 8 in the prototype).
	const navItems: NavItem[] = [
		{ label: 'Resumen', href: '/', icon: 'layers' },
		{ label: 'Feed', href: '/feed', icon: 'feed' },
		{ label: 'Campo', href: '/campo', icon: 'field' },
		{ label: 'Eventos', href: '/events', icon: 'events' },
		{ label: 'Agenda', href: '/agenda', icon: 'agenda' },
		{ label: 'Actores', href: '/persons', icon: 'people' },
		{ label: 'Consultas', href: '/consultas', icon: 'query' },
		{ label: 'Estadísticas', href: '/stats', icon: 'stats' },
		{ label: 'Búsquedas', href: '/saved-searches', icon: 'search' },
		{ label: 'Revisiones', href: '/revisiones', icon: 'check' },
		{ label: 'Configuración', href: '/settings', icon: 'settings' }
	];

	let collapsed = $state(false);
	let menuOpen = $state(false);

	let sidebarEl: HTMLElement | undefined = $state();
	let menuButton: HTMLButtonElement | undefined = $state();
	let closeButton: HTMLButtonElement | undefined = $state();
	let panelOpen = $state(false);
	let panelQuestion = $state('');
	let citationsOpen = $state(false);
	const VISIBLE_CITATIONS = 3;
	let panelPending = $state(false);
	let panelError = $state('');
	let panelResult: {
		question: string;
		answer: string;
		citations: { title: string | null; url: string }[];
	} | null = $state(null);
	let queryInput: HTMLTextAreaElement | undefined = $state();
	let launcherButton: HTMLButtonElement | undefined = $state();

	function isActive(href: string): boolean {
		const path = page.url.pathname;
		return href === '/' ? path === '/' : path === href || path.startsWith(`${href}/`);
	}

	function toggleCollapsed(): void {
		collapsed = !collapsed;
	}

	function openMenu(): void {
		menuOpen = true;
	}

	function closeMenu(restoreFocus = false): void {
		if (!menuOpen) return;
		menuOpen = false;
		if (restoreFocus) menuButton?.focus();
	}

	function togglePanel(): void {
		panelOpen = !panelOpen;
	}

	function closePanel(restoreFocus = false): void {
		if (!panelOpen) return;
		panelOpen = false;
		if (restoreFocus) launcherButton?.focus();
	}

	// The panel asks the REAL /consultas action (the same handler the page
	// uses) and renders answer + citations in place; no navigation, no fake data.
	const panelEnhance: SubmitFunction = ({ formData }) => {
		const question = String((formData.get('question') ?? '') as string).trim();
		panelQuestion = question;
		panelResult = null;
		citationsOpen = false;
		panelPending = true;
		panelError = '';
		if (queryInput) queryInput.value = '';
		return async ({ result, update }) => {
			if (result.type === 'success') {
				const data = (result.data ?? {}) as Record<string, unknown>;
				if (data.error) {
					panelError = String(data.error);
				} else {
					const raw = Array.isArray(data.citations) ? data.citations : [];
					panelResult = {
						question: String(data.question ?? ''),
						answer: typeof data.answer === 'string' ? data.answer : '',
						citations: raw
							.map((c) => {
								const e = c as { title?: unknown; url?: unknown };
								return { title: typeof e.title === 'string' ? e.title : null, url: typeof e.url === 'string' ? e.url : '' };
							})
							.filter((c) => c.url !== '')
					};
				}
			} else if (result.type === 'error') {
				panelError = 'No se pudo consultar la pregunta.';
			}
			panelPending = false;
			await update({ reset: false });
		};
	};

	function handleComposerKeydown(event: KeyboardEvent): void {
		if (event.key === 'Enter' && !event.shiftKey) {
			event.preventDefault();
			(event.currentTarget as HTMLTextAreaElement).form?.requestSubmit();
		}
	}

	function handleKeydown(event: KeyboardEvent): void {
		if (event.key === 'Escape' && panelOpen) {
			event.preventDefault();
			closePanel(true);
			return;
		}
		if (!menuOpen) return;
		if (event.key === 'Escape') {
			event.preventDefault();
			closeMenu(true);
			return;
		}
		if (event.key !== 'Tab' || !sidebarEl) return;
		const focusables = [
			...sidebarEl.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')
		];
		if (focusables.length === 0) return;
		const first = focusables[0];
		const last = focusables[focusables.length - 1];
		const active = document.activeElement;
		if (event.shiftKey && active === first) {
			event.preventDefault();
			last.focus();
		} else if (!event.shiftKey && active === last) {
			event.preventDefault();
			first.focus();
		}
	}

	$effect(() => {
		document.body.classList.toggle('sidebar-collapsed', collapsed);
	});

	$effect(() => {
		document.body.classList.toggle('mobile-nav-open', menuOpen);
	});

	// The drawer owns focus while open: the rest of the shell goes inert and
	// the close control receives focus (mockup behavior).
	$effect(() => {
		if (menuOpen) closeButton?.focus();
	});

	$effect(() => {
		if (panelOpen) queryInput?.focus();
	});

	$effect(() => {
		const query = window.matchMedia('(min-width: 769px)');
		const onChange = (event: MediaQueryListEvent): void => {
			if (event.matches) closeMenu(false);
		};
		query.addEventListener('change', onChange);
		return () => query.removeEventListener('change', onChange);
	});
</script>

<svelte:window onkeydown={handleKeydown} />

<div class="shell">
	<aside
		id="app-sidebar"
		class="sidebar"
		class:mobile-open={menuOpen}
		aria-label="Navegación principal"
		bind:this={sidebarEl}
	>
		<div class="sidebar-head">
			<button
				type="button"
				class="sidebar-toggle"
				aria-controls="app-sidebar"
				aria-expanded={!collapsed}
				aria-label={collapsed ? 'Expandir menú' : 'Contraer menú'}
				title={collapsed ? 'Expandir menú' : 'Contraer menú'}
				onclick={toggleCollapsed}
			>
				<span class="sidebar-toggle-arrow" aria-hidden="true">{collapsed ? '›' : '‹'}</span>
			</button>
			<div class="brand">
				<img
					class="brand-logo"
					src="/brand/mine-logo.png"
					width="1983"
					height="793"
					alt="Monitoreo Integral"
				/>
				<img
					class="brand-logo-compact"
					src="/brand/mine-monogram.png"
					width="1254"
					height="1254"
					alt="Monitoreo Integral"
				/>
			</div>
		</div>

		<button type="button" class="mobile-menu-close" aria-label="Cerrar menú" onclick={() => closeMenu()} bind:this={closeButton}>
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.close} /></svg>
		</button>

		<div>
			<nav class="nav" aria-label="Secciones">
				{#each navItems as item (item.href)}
					<a
						href={item.href}
						class="nav-button"
						class:active={isActive(item.href)}
						aria-current={isActive(item.href) ? 'page' : undefined}
						aria-label={collapsed ? item.label : undefined}
						title={collapsed ? item.label : undefined}
						onclick={() => closeMenu()}
					>
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS[item.icon]} /></svg>
						<span class="nav-label">{item.label}</span>
					</a>
				{/each}
			</nav>
		</div>

		<div class="sidebar-version" aria-label={`Versión de la plataforma ${APP_VERSION}`}>
			<span class="sidebar-version-number">Versión {APP_VERSION}</span>
		</div>
	</aside>

	<div class="main-shell" inert={menuOpen}>
		<header class="mobile-header">
			<button
				type="button"
				class="mobile-menu"
				aria-label={menuOpen ? 'Cerrar menú' : 'Abrir menú'}
				aria-controls="app-sidebar"
				aria-expanded={menuOpen}
				onclick={() => (menuOpen ? closeMenu() : openMenu())}
				bind:this={menuButton}
			>
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.menu} /></svg>
			</button>
			<img
				class="mobile-header-logo"
				src="/brand/mine-logo.png"
				width="1983"
				height="793"
				alt="Monitoreo Integral"
			/>
		</header>

		<main class="main">
			{@render children?.()}
		</main>
	</div>
</div>

{#if page.url.pathname !== '/consultas'}
		<button
			type="button"
			class="query-launcher"
			aria-expanded={panelOpen}
			aria-controls="floating-query"
			onclick={togglePanel}
			bind:this={launcherButton}
			inert={menuOpen || undefined}
		>
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.query} /></svg>
			Consultas
		</button>
		{#if panelOpen}
			<section class="floating-query" id="floating-query" aria-labelledby="floating-query-title">
				<header class="floating-query-head">
					<span class="query-chat-mark" aria-hidden="true">
						<svg class="od-icon" viewBox="0 0 24 24"><path d={ICONS.query} /></svg>
					</span>
					<div class="floating-query-title">
						<h2 id="floating-query-title">De la pregunta a la fuente</h2>
						<p>Consulta tu monitoreo</p>
					</div>
					<a class="text-link" href="/consultas" onclick={() => closePanel()}>Abrir página</a>
					<button type="button" class="icon-button" aria-label="Cerrar consultas" onclick={() => closePanel(true)}>
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.close} /></svg>
					</button>
				</header>
				<div class="floating-query-body">
					<div class="floating-query-answer" aria-live="polite">
						{#if panelError}
							<p class="floating-error" role="alert">{panelError}</p>
						{/if}
						{#if panelQuestion}
							<div class="query-question">
								<span>Tu pregunta</span>
								<p>{panelQuestion}</p>
							</div>
							{#if panelPending}
								<p class="thinking" role="status">Pensando…</p>
							{/if}
							<article class="answer">
								<h3>Respuesta</h3>
								<p>{panelResult?.answer ?? ''}</p>
							</article>
							{#if (panelResult?.citations?.length ?? 0) > 0}
								<div class="evidence">
									<ul>
										{#each (panelResult?.citations ?? []).slice(0, citationsOpen ? undefined : VISIBLE_CITATIONS) as citation (citation.url + citation.title)}
											<li>
												<a href={citation.url} target="_blank" rel="noopener noreferrer">
													{citation.title ?? citation.url}
												</a>
											</li>
										{/each}
									</ul>
									{#if (panelResult?.citations?.length ?? 0) > VISIBLE_CITATIONS}
										<button
											type="button"
											class="text-link citations-toggle"
											onclick={() => (citationsOpen = !citationsOpen)}
										>
											{citationsOpen
												? 'ocultar'
												: `…${(panelResult?.citations?.length ?? 0) - VISIBLE_CITATIONS} fuentes más — ver`}
										</button>
									{/if}
								</div>
							{/if}
						{:else if !panelPending && !panelResult}
						<div class="floating-query-welcome">
							<span class="query-welcome-icon" aria-hidden="true">
								<svg class="od-icon" viewBox="0 0 24 24"><path d={ICONS.query} /></svg>
							</span>
							<h3>¿Qué quieres investigar?</h3>
							<p>Explora las menciones y abre la evidencia de cada resultado.</p>
						</div>
					{/if}
					</div>

					<form
						method="POST"
						action="/consultas"
						class="floating-query-composer"
						use:enhance={panelEnhance}
					>
						<label class="sr-only" for="floating-query-input">Escribe tu pregunta</label>
						<div class="floating-query-composer-field">
							<textarea
								id="floating-query-input"
							name="question"
								rows="2"
								placeholder="Pregunta sobre tu monitoreo..."
								bind:this={queryInput}
								onkeydown={handleComposerKeydown}
							></textarea>
							<button class="button primary" type="submit" aria-label="Enviar consulta" disabled={panelPending}>
								<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICONS.arrow} /></svg>
							</button>
						</div>
						<p>Cada respuesta cita las notas que la sustentan.</p>
					</form>
				</div>
			</section>
		{/if}
{/if}
