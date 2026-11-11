<script lang="ts">
	import '../app.css';
	import { onMount, onDestroy } from 'svelte';
	import { slide } from 'svelte/transition';
	import { page } from '$app/stores';
	import { goto } from '$app/navigation';
	import { tiltsState, connectWebSocket, disconnectWebSocket, startHeaterPolling, stopHeaterPolling } from '$lib/stores/tilts.svelte';
	import { loadConfig, configState, getTempUnit } from '$lib/stores/config.svelte';
	import { weatherState, startWeatherPolling, stopWeatherPolling, getWeatherIcon, formatDayName } from '$lib/stores/weather.svelte';
	import { initAuth, authState } from '$lib/stores/auth.svelte';
	import { signOut } from '$lib/supabase';
	import { config, configStores, fetchAppConfig } from '$lib/config';
	import { get } from 'svelte/store';
	import Brand from '$lib/components/shell/Brand.svelte';
	import ThemeToggle from '$lib/components/shell/ThemeToggle.svelte';
	import { SHOW_THEME_TOGGLE, initTheme } from '$lib/stores/theme.svelte';

	// Create reactive state from config stores (Svelte 5 pattern)
	let authRequired = $state(false);
	let authEnabled = $state(false);
	let configInitialized = $state(false);

	// Subscribe to config stores in onMount for proper cleanup
	let unsubscribes: Array<() => void> = [];

	function setupConfigSubscriptions() {
		unsubscribes.push(
			configStores.authRequired.subscribe(v => authRequired = v),
			configStores.authEnabled.subscribe(v => authEnabled = v),
			configStores.initialized.subscribe(v => configInitialized = v)
		);
	}

	// Format ambient temp based on user's unit preference
	function formatAmbientTemp(tempC: number): string {
		if (configState.config.temp_units === 'F') {
			return ((tempC * 9) / 5 + 32).toFixed(1);
		}
		return tempC.toFixed(1);
	}

	// Format forecast temp
	function formatForecastTemp(temp: number | null): string {
		if (temp === null) return '--';
		return Math.round(temp).toString();
	}

	let { children } = $props();
	let moreOpen = $state(false);
	let weatherDropdownOpen = $state(false);
	let userMenuOpen = $state(false);
	let signingOut = $state(false);

	// Derived: show heater indicator only when HA is enabled and heater entity is configured
	let showHeaterIndicator = $derived(
		configState.config.ha_enabled && configState.config.ha_heater_entity_id
	);

	// Get today's forecast
	let todayForecast = $derived(weatherState.forecast[0] || null);

	// Check if current route is the login page
	let isLoginPage = $derived($page.url.pathname === '/login');

	// Redirect to login if not authenticated (cloud mode with auth required only)
	$effect(() => {
		if (authRequired && authState.initialized && !authState.user && !isLoginPage) {
			goto('/login');
		}
	});

	// Track if services have been started (to avoid duplicate starts)
	let servicesStarted = $state(false);

	// Start authenticated services only when appropriate
	function startAuthenticatedServices() {
		if (servicesStarted) return;
		servicesStarted = true;

		loadConfig();
		connectWebSocket();
		startHeaterPolling(30000);
		startWeatherPolling(30 * 60 * 1000);
	}

	// Effect to start services when auth state is ready
	$effect(() => {
		// Don't start until config is initialized
		if (!configInitialized) return;

		// Don't start until auth is initialized
		if (!authState.initialized) return;

		// In cloud mode with required auth, wait until user is authenticated
		if (authRequired && !authState.user) return;

		// Otherwise (local mode or authenticated), start services
		startAuthenticatedServices();
	});

	onMount(async () => {
		initTheme();
		// Set up config store subscriptions
		setupConfigSubscriptions();

		// Fetch app config from backend (includes Supabase credentials)
		await fetchAppConfig();

		// Initialize auth (uses app config for Supabase client)
		await initAuth();

		// Services will be started by the $effect above once auth is ready
	});

	async function handleSignOut() {
		signingOut = true;
		try {
			await signOut();
			goto('/login');
		} finally {
			signingOut = false;
			userMenuOpen = false;
		}
	}

	function toggleUserMenu() {
		userMenuOpen = !userMenuOpen;
	}

	function closeUserMenu() {
		userMenuOpen = false;
	}

	onDestroy(() => {
		// Clean up config store subscriptions
		unsubscribes.forEach(unsub => unsub());

		disconnectWebSocket();
		stopHeaterPolling();
		stopWeatherPolling();
	});

	function toggleWeatherDropdown() {
		weatherDropdownOpen = !weatherDropdownOpen;
	}

	function closeWeatherDropdown() {
		weatherDropdownOpen = false;
	}

	// Base nav links (always shown)
	const baseNavLinks = [
		{ href: '/', label: 'Home' },
		{ href: '/batches', label: 'Batches' },
		{ href: '/recipes', label: 'Recipes' },
		{ href: '/inventory', label: 'Inventory' },
		{ href: '/library', label: 'Library' }
	];

	// Dynamic nav links based on config
	let navLinks = $derived([
		...baseNavLinks,
		// Only show Assistant when AI is enabled
		...(configState.config.ai_enabled ? [{ href: '/assistant', label: 'Assistant' }, { href: '/knowledge', label: 'Knowledge' }] : []),
		{ href: '/system', label: 'System' }
	]);

	function isActive(href: string, pathname: string): boolean {
		if (href === '/') return pathname === '/';
		return pathname.startsWith(href);
	}

	// Phone bottom tabs; everything else in navLinks goes under "More"
	const tabHrefs = ['/', '/batches', '/recipes', '/inventory'];
	let moreLinks = $derived(navLinks.filter((l) => !tabHrefs.includes(l.href)));
	let moreActive = $derived(moreLinks.some((l) => isActive(l.href, $page.url.pathname)));

	// Close the More sheet on navigation
	$effect(() => {
		$page.url.pathname;
		moreOpen = false;
	});
</script>

<svelte:head>
	<title>BrewSignal</title>
	<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
</svelte:head>

<div class="layout-container">
	<header class="topbar">
		<Brand />

		<nav class="primary-nav" aria-label="Primary">
			{#each navLinks as link}
				<a
					href={link.href}
					class="nav-link"
					aria-current={isActive(link.href, $page.url.pathname) ? 'page' : undefined}
				>
					{link.label}
				</a>
			{/each}
		</nav>

		<div class="topbar-controls">
			{#if todayForecast}
				<div class="chip-wrapper weather-wrapper">
					<button
						type="button"
						class="chip chip-button"
						onclick={toggleWeatherDropdown}
						aria-label="Toggle weather forecast"
						aria-expanded={weatherDropdownOpen}
					>
						<span class="chip-icon">{getWeatherIcon(todayForecast.condition)}</span>
						<span class="num">{formatForecastTemp(todayForecast.temperature)}°</span>
					</button>

					{#if weatherDropdownOpen}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<!-- svelte-ignore a11y_click_events_have_key_events -->
						<div class="backdrop" onclick={closeWeatherDropdown}></div>
						<div class="dropdown weather-dropdown" transition:slide={{ duration: 150 }}>
							<div class="dropdown-header">5-Day Forecast</div>
							<div class="weather-days">
								{#each weatherState.forecast.slice(0, 5) as day}
									<div class="weather-day">
										<span class="weather-day-name">{formatDayName(day.datetime)}</span>
										<span class="weather-day-icon">{getWeatherIcon(day.condition)}</span>
										<span class="num weather-temps">
											<span class="temp-high">{formatForecastTemp(day.temperature)}°</span>
											<span class="temp-low">{formatForecastTemp(day.templow)}°</span>
										</span>
									</div>
								{/each}
							</div>
						</div>
					{/if}
				</div>
			{/if}

			{#if tiltsState.ambient && (tiltsState.ambient.temperature !== null || tiltsState.ambient.humidity !== null)}
				<div class="chip ambient-chip num" title="Ambient">
					{#if tiltsState.ambient.temperature !== null}
						<span>{formatAmbientTemp(tiltsState.ambient.temperature)}{getTempUnit()}</span>
					{/if}
					{#if tiltsState.ambient.humidity !== null}
						<span>{tiltsState.ambient.humidity.toFixed(0)}%</span>
					{/if}
				</div>
			{/if}

			{#if showHeaterIndicator && tiltsState.heater.available}
				<div class="chip heater-chip" class:heater-on={tiltsState.heater.state === 'on'} title="Heater">
					<span class="dot" aria-hidden="true"></span>
					<span class="chip-text num">{tiltsState.heater.state === 'on' ? 'Heating' : 'Heater off'}</span>
				</div>
			{/if}

			<div class="status" title={tiltsState.connected ? 'Live' : 'Offline'}>
				<span class="dot" class:connected={tiltsState.connected} aria-hidden="true"></span>
				<span class="status-text num">{tiltsState.connected ? 'Live' : 'Offline'}</span>
			</div>

			{#if SHOW_THEME_TOGGLE}
				<!-- Hidden until all screens use the new tokens: bead tilt_ui-nv1r -->
				<ThemeToggle />
			{/if}

			{#if authEnabled && authState.user}
				<div class="chip-wrapper">
					<button
						type="button"
						class="icon-btn"
						onclick={toggleUserMenu}
						aria-label="User menu"
						aria-expanded={userMenuOpen}
					>
						<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true">
							<path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
						</svg>
					</button>
					{#if userMenuOpen}
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<!-- svelte-ignore a11y_click_events_have_key_events -->
						<div class="backdrop" onclick={closeUserMenu}></div>
						<div class="dropdown user-dropdown" transition:slide={{ duration: 150 }}>
							<div class="user-email">{authState.user?.email}</div>
							<button type="button" class="menu-item" onclick={handleSignOut} disabled={signingOut}>
								{signingOut ? 'Signing out...' : 'Sign out'}
							</button>
						</div>
					{/if}
				</div>
			{:else if authEnabled && !authRequired && authState.initialized}
				<a href="/login" class="sign-in-link">Sign in</a>
			{/if}
		</div>
	</header>

	<main class="page">
		{#if !configInitialized}
			<div class="auth-loading">
				<div class="auth-loading-spinner"></div>
				<p>Loading...</p>
			</div>
		{:else if authRequired && !authState.initialized}
			<div class="auth-loading">
				<div class="auth-loading-spinner"></div>
				<p>Loading...</p>
			</div>
		{:else if authRequired && !authState.user && !isLoginPage}
			<div class="auth-loading">
				<p>Redirecting to login...</p>
			</div>
		{:else}
			{@render children()}
		{/if}
	</main>

	<!-- Phone bottom tab bar -->
	<nav class="tabbar" aria-label="Mobile navigation">
		{#if moreOpen}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<div class="more-backdrop" onclick={() => (moreOpen = false)}></div>
			<div class="more-sheet" id="more-sheet">
				{#each moreLinks as link}
					<a
						href={link.href}
						class="more-link"
						aria-current={isActive(link.href, $page.url.pathname) ? 'page' : undefined}
					>
						{link.label}
					</a>
				{/each}
			</div>
		{/if}
		<div class="tabs">
			<a href="/" class="tab" aria-current={isActive('/', $page.url.pathname) ? 'page' : undefined}>
				<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3 9.5L10 3.5l7 6V17H3V9.5z" /></svg>
				<span>Home</span>
			</a>
			<a href="/batches" class="tab" aria-current={isActive('/batches', $page.url.pathname) ? 'page' : undefined}>
				<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><rect x="5" y="3" width="10" height="14" rx="1.5" /><line x1="5" y1="8" x2="15" y2="8" /></svg>
				<span>Batches</span>
			</a>
			<a href="/recipes" class="tab" aria-current={isActive('/recipes', $page.url.pathname) ? 'page' : undefined}>
				<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><line x1="4" y1="6" x2="16" y2="6" /><line x1="4" y1="10" x2="16" y2="10" /><line x1="4" y1="14" x2="12" y2="14" /></svg>
				<span>Recipes</span>
			</a>
			<a href="/inventory" class="tab" aria-current={isActive('/inventory', $page.url.pathname) ? 'page' : undefined}>
				<svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M3.5 6.5L10 3l6.5 3.5v7L10 17l-6.5-3.5v-7z" /></svg>
				<span>Inventory</span>
			</a>
			<button
				type="button"
				class="tab"
				class:current={moreActive || moreOpen}
				aria-expanded={moreOpen}
				aria-controls="more-sheet"
				onclick={() => (moreOpen = !moreOpen)}
			>
				<svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><circle cx="5" cy="10" r="1.2" /><circle cx="10" cy="10" r="1.2" /><circle cx="15" cy="10" r="1.2" /></svg>
				<span>More</span>
			</button>
		</div>
	</nav>
</div>

<style>
	.layout-container {
		min-height: 100vh;
		background: var(--bg-canvas);
		color: var(--ink-primary);
	}

	/* Top bar */
	.topbar {
		position: sticky;
		top: 0;
		z-index: 30;
		display: grid;
		grid-template-columns: auto minmax(0, 1fr) auto;
		align-items: center;
		gap: var(--space-lg);
		height: 56px;
		padding: 0 var(--space-lg);
		background: var(--bg-canvas);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.primary-nav {
		display: flex;
		align-items: center;
		gap: var(--space-2xs);
		height: 100%;
		min-width: 0;
		overflow-x: auto;
		scrollbar-width: none;
	}
	.primary-nav::-webkit-scrollbar {
		display: none;
	}

	.nav-link {
		position: relative;
		display: inline-flex;
		align-items: center;
		height: 100%;
		padding: 0 var(--space-sm);
		white-space: nowrap;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 500;
		color: var(--ink-secondary);
		transition: color 160ms var(--ease-out-quart);
	}
	.nav-link:hover {
		color: var(--ink-primary);
	}
	.nav-link[aria-current='page'] {
		color: var(--ink-primary);
		font-weight: 600;
	}
	.nav-link[aria-current='page']::after {
		content: '';
		position: absolute;
		left: var(--space-sm);
		right: var(--space-sm);
		bottom: -1px;
		height: 2px;
		background: var(--accent);
	}

	.topbar-controls {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}

	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
	}

	/* Chips: hairline-outlined indicators */
	.chip {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		min-height: 28px;
		padding: 0 var(--space-xs);
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		background: transparent;
		color: var(--ink-secondary);
		font-size: var(--text-xs);
	}
	.chip-button {
		cursor: pointer;
		transition: border-color 150ms var(--ease-out-quart), color 150ms var(--ease-out-quart);
	}
	.chip-button:hover {
		border-color: var(--rule-strong);
		color: var(--ink-primary);
	}
	.ambient-chip {
		gap: var(--space-xs);
	}
	.heater-chip.heater-on {
		border-color: var(--accent-rule);
		color: var(--accent);
	}
	.heater-chip.heater-on .dot {
		background: var(--accent);
	}

	.dot {
		width: 7px;
		height: 7px;
		border-radius: 50%;
		background: var(--ink-muted);
		flex-shrink: 0;
	}
	.status {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.status .dot.connected {
		background: var(--status-steady);
	}

	.icon-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		background: transparent;
		color: var(--ink-secondary);
		cursor: pointer;
		transition: border-color 150ms var(--ease-out-quart), color 150ms var(--ease-out-quart);
	}
	.icon-btn:hover {
		border-color: var(--rule-strong);
		color: var(--ink-primary);
	}

	.sign-in-link {
		display: inline-flex;
		align-items: center;
		min-height: 36px;
		padding: 0 var(--space-sm);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--accent);
		transition: background 150ms var(--ease-out-quart);
	}
	.sign-in-link:hover {
		background: var(--accent-tint);
	}

	/* Dropdowns */
	.chip-wrapper {
		position: relative;
	}
	.backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
	}
	.dropdown {
		position: absolute;
		top: calc(100% + var(--space-2xs));
		right: 0;
		z-index: 50;
		background: var(--bg-elevated);
		border: 1px solid var(--rule-strong);
		border-radius: 6px;
	}
	.dropdown-header {
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		letter-spacing: 0.04em;
		text-transform: uppercase;
		color: var(--ink-muted);
	}
	.weather-dropdown {
		min-width: 17rem;
	}
	.weather-days {
		display: flex;
		flex-direction: column;
	}
	.weather-day {
		display: grid;
		grid-template-columns: 1fr auto auto;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
	}
	.weather-day:last-child {
		border-bottom: none;
	}
	.weather-temps {
		display: inline-flex;
		gap: var(--space-xs);
	}
	.temp-high {
		color: var(--ink-primary);
	}
	.temp-low {
		color: var(--ink-muted);
	}
	.user-dropdown {
		min-width: 13rem;
	}
	.user-email {
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.menu-item {
		display: block;
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-sm);
		background: transparent;
		border: none;
		text-align: left;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		cursor: pointer;
		transition: background 150ms var(--ease-out-quart), color 150ms var(--ease-out-quart);
	}
	.menu-item:hover {
		background: var(--bg-subtle);
		color: var(--ink-primary);
	}
	.menu-item:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Page frame */
	.page {
		max-width: 1280px;
		margin: 0 auto;
		padding: var(--space-lg);
	}

	.tabbar {
		display: none;
	}

	/* Auth loading */
	.auth-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-height: 50vh;
		color: var(--ink-muted);
	}
	.auth-loading-spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: var(--space-md);
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	/* Tablet: nav scrolls, secondary status text hidden */
	@media (max-width: 1040px) {
		.topbar {
			gap: var(--space-md);
		}
		.nav-link {
			padding: 0 var(--space-xs);
		}
		.nav-link[aria-current='page']::after {
			left: var(--space-xs);
			right: var(--space-xs);
		}
		.status-text,
		.chip-text,
		.ambient-chip {
			display: none;
		}
	}

	/* Phone: compact bar + bottom tabs */
	@media (max-width: 760px) {
		.topbar {
			grid-template-columns: 1fr auto;
			height: 52px;
			padding: 0 var(--space-md);
		}
		.primary-nav,
		.weather-wrapper,
		.ambient-chip,
		.heater-chip {
			display: none;
		}
		.page {
			padding: var(--space-md);
			padding-bottom: calc(60px + env(safe-area-inset-bottom) + var(--space-md));
		}

		.tabbar {
			display: block;
			position: fixed;
			left: 0;
			right: 0;
			bottom: 0;
			z-index: 40;
			background: var(--bg-surface);
			border-top: 1px solid var(--rule-strong);
			padding-bottom: env(safe-area-inset-bottom);
		}
		.tabs {
			display: grid;
			grid-template-columns: repeat(5, 1fr);
			height: 60px;
		}
		.tab {
			position: relative;
			display: flex;
			flex-direction: column;
			align-items: center;
			justify-content: center;
			gap: 3px;
			min-height: 48px;
			background: transparent;
			border: none;
			font-family: var(--font-display);
			font-size: 0.6875rem;
			font-weight: 600;
			color: var(--ink-secondary);
			cursor: pointer;
			transition: color 150ms var(--ease-out-quart);
		}
		.tab svg {
			width: 18px;
			height: 18px;
		}
		.tab[aria-current='page'],
		.tab.current {
			color: var(--accent);
		}
		.tab[aria-current='page']::before,
		.tab.current::before {
			content: '';
			position: absolute;
			top: 0;
			left: 24%;
			right: 24%;
			height: 2px;
			background: var(--accent);
		}
		.more-backdrop {
			position: fixed;
			inset: 0;
			bottom: calc(60px + env(safe-area-inset-bottom));
			z-index: -1;
		}
		.more-sheet {
			position: absolute;
			left: 0;
			right: 0;
			bottom: 100%;
			display: grid;
			background: var(--bg-elevated);
			border-top: 1px solid var(--rule-strong);
		}
		.more-link {
			display: flex;
			align-items: center;
			min-height: 48px;
			padding: 0 var(--space-md);
			border-bottom: 1px solid var(--rule-hairline);
			font-family: var(--font-display);
			font-size: var(--text-base);
			font-weight: 500;
			color: var(--ink-secondary);
		}
		.more-link:last-child {
			border-bottom: none;
		}
		.more-link[aria-current='page'] {
			color: var(--accent);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		* {
			transition-duration: 0.01ms !important;
		}
		.auth-loading-spinner {
			animation-duration: 2s;
		}
	}
</style>
