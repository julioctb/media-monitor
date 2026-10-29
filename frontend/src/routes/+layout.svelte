<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import { enhance } from '$app/forms';
	import pkg from '../../package.json';
	import type { LayoutProps } from './$types';
	import type { SubmitFunction } from './consultas/$types';
	import { ICON_PATHS } from '$lib/icons';
	import Toaster from '$lib/components/Toaster.svelte';

	let { children }: LayoutProps = $props();

	const APP_VERSION: string = pkg.version;

	interface NavItem {
		label: string;
		href: string;
		icon: keyof typeof ICON_PATHS;
	}

	// Icon paths from the v3 mockup (app.js `paths` map); `stats` added in the
	// same 24px stroke language for the three routes the mockup lacks.

	// Nav per the v3 contract (Panel-de-monitoreo-informativo app.js labels):
	// exactly these eight views, this order. Legacy routes (/stats,
	// /saved-searches, /revisiones) stay reachable by URL but are not part
	// of the v3 menu.
	const navItems: NavItem[] = [
		{ label: 'Resumen diario', href: '/', icon: 'layers' },
		{ label: 'Feed de noticias', href: '/feed', icon: 'feed' },
		{ label: 'Eventos', href: '/events', icon: 'events' },
		{ label: 'Agenda', href: '/agenda', icon: 'agenda' },
		{ label: 'Personajes', href: '/persons', icon: 'people' },
		{ label: 'Campo', href: '/campo', icon: 'field' },
		{ label: 'Consultas', href: '/consultas', icon: 'query' },
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
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.close} /></svg>
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
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS[item.icon]} /></svg>
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
				<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.menu} /></svg>
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
			<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.query} /></svg>
			Consultas
		</button>
		{#if panelOpen}
			<section class="floating-query" id="floating-query" aria-labelledby="floating-query-title">
				<header class="floating-query-head">
					<span class="query-chat-mark" aria-hidden="true">
						<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.query} /></svg>
					</span>
					<div class="floating-query-title">
						<h2 id="floating-query-title">De la pregunta a la fuente</h2>
						<p>Consulta tu monitoreo</p>
					</div>
					<a class="text-link" href="/consultas" onclick={() => closePanel()}>Abrir página</a>
					<button type="button" class="icon-button" aria-label="Cerrar consultas" onclick={() => closePanel(true)}>
						<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.close} /></svg>
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
								<svg class="od-icon" viewBox="0 0 24 24"><path d={ICON_PATHS.query} /></svg>
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
								<svg class="od-icon" viewBox="0 0 24 24" aria-hidden="true"><path d={ICON_PATHS.arrow} /></svg>
							</button>
						</div>
						<p>Cada respuesta cita las notas que la sustentan.</p>
					</form>
				</div>
			</section>
		{/if}
{/if}

<!-- Single toast outlet (mockup #toast): preference copy, 3.5 s. -->
<Toaster />
