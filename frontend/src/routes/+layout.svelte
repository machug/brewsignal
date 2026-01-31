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
	let mobileMenuOpen = $state(false);
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
		{ href: '/', label: 'Dashboard' },
		{ href: '/batches', label: 'Batches' },
		{ href: '/recipes', label: 'Recipes' },
		{ href: '/inventory', label: 'Inventory' },
		{ href: '/library', label: 'Library' }
	];

	// Dynamic nav links based on config
	let navLinks = $derived([
		...baseNavLinks,
		// Only show Assistant when AI is enabled
		...(configState.config.ai_enabled ? [{ href: '/assistant', label: 'Assistant' }] : []),
		{ href: '/system', label: 'System' }
	]);

	function isActive(href: string, pathname: string): boolean {
		if (href === '/') return pathname === '/';
		return pathname.startsWith(href);
	}

	function closeMobileMenu() {
		mobileMenuOpen = false;
	}
</script>

<svelte:head>
	<title>BrewSignal</title>
	<meta name="viewport" content="width=device-width, initial-scale=1" />
</svelte:head>

<div class="layout-container">
	<!-- Navigation -->
	<nav class="main-nav">
		<div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
			<div class="flex items-center justify-between h-16">
				<!-- Logo -->
				<a href="/" class="flex items-center gap-3 group">
					<div class="logo-icon">
						<span class="text-lg">🍺</span>
					</div>
					<span class="logo-text">
						Brew<span class="logo-accent">Signal</span>
					</span>
				</a>

				<!-- Desktop navigation -->
				<div class="hidden md:flex items-center gap-1">
					{#each navLinks as link}
						{@const active = isActive(link.href, $page.url.pathname)}
						<a
							href={link.href}
							class="nav-link {active ? 'active' : ''}"
						>
							{link.label}
						</a>
					{/each}
				</div>

				<!-- Right side: weather + ambient + heater indicator + connection status + mobile menu -->
				<div class="flex items-center gap-3">
					<!-- Weather indicator with dropdown -->
					{#if todayForecast}
						<div class="weather-indicator-wrapper">
							<button
								type="button"
								class="weather-indicator"
								onclick={toggleWeatherDropdown}
								aria-label="Toggle weather forecast"
								aria-expanded={weatherDropdownOpen}
							>
								<span class="text-sm">{getWeatherIcon(todayForecast.condition)}</span>
								<span class="indicator-text">
									{formatForecastTemp(todayForecast.temperature)}°
								</span>
							</button>

							{#if weatherDropdownOpen}
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<!-- svelte-ignore a11y_click_events_have_key_events -->
								<div class="weather-backdrop" onclick={closeWeatherDropdown}></div>
								<div class="weather-dropdown" transition:slide={{ duration: 150 }}>
									<div class="weather-dropdown-header">
										<span>5-Day Forecast</span>
									</div>
									<div class="weather-dropdown-days">
										{#each weatherState.forecast.slice(0, 5) as day}
											<div class="weather-day">
												<span class="weather-day-name">{formatDayName(day.datetime)}</span>
												<span class="weather-day-icon">{getWeatherIcon(day.condition)}</span>
												<div class="weather-day-temps">
													<span class="weather-temp-high">{formatForecastTemp(day.temperature)}°</span>
													<span class="weather-temp-low">{formatForecastTemp(day.templow)}°</span>
												</div>
											</div>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/if}

					<!-- Ambient temperature/humidity -->
					{#if tiltsState.ambient && (tiltsState.ambient.temperature !== null || tiltsState.ambient.humidity !== null)}
						<div class="ambient-indicator">
							{#if tiltsState.ambient.temperature !== null}
								<div class="flex items-center gap-1.5">
									<span class="text-sm opacity-60">🌡️</span>
									<span class="indicator-text">
										{formatAmbientTemp(tiltsState.ambient.temperature)}{getTempUnit()}
									</span>
								</div>
							{/if}
							{#if tiltsState.ambient.humidity !== null}
								<div class="flex items-center gap-1.5">
									<span class="text-sm opacity-60">💧</span>
									<span class="indicator-text">
										{tiltsState.ambient.humidity.toFixed(0)}%
									</span>
								</div>
							{/if}
						</div>
					{/if}

					<!-- Heater indicator -->
					{#if showHeaterIndicator && tiltsState.heater.available}
						<div class="heater-indicator" class:heater-on={tiltsState.heater.state === 'on'}>
							<span class="heater-icon">🔥</span>
							<span class="heater-text">
								{tiltsState.heater.state === 'on' ? 'Heating' : 'Off'}
							</span>
						</div>
					{/if}

					<!-- Connection status -->
					<div class="connection-indicator">
						<span class="connection-dot" class:connected={tiltsState.connected}></span>
						<span class="connection-text">
							{tiltsState.connected ? 'Live' : 'Offline'}
						</span>
					</div>

					<!-- User menu (shown when authenticated with Supabase) -->
					{#if authEnabled && authState.user}
						<div class="user-menu-wrapper">
							<button
								type="button"
								class="user-menu-btn"
								onclick={toggleUserMenu}
								aria-label="User menu"
							>
								<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
									<path stroke-linecap="round" stroke-linejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
								</svg>
							</button>
							{#if userMenuOpen}
								<!-- svelte-ignore a11y_no_static_element_interactions -->
								<!-- svelte-ignore a11y_click_events_have_key_events -->
								<div class="user-menu-backdrop" onclick={closeUserMenu}></div>
								<div class="user-menu-dropdown" transition:slide={{ duration: 150 }}>
									<div class="user-menu-email">{authState.user?.email}</div>
									<button
										type="button"
										class="user-menu-item"
										onclick={handleSignOut}
										disabled={signingOut}
									>
										{signingOut ? 'Signing out...' : 'Sign out'}
									</button>
								</div>
							{/if}
						</div>
					{:else if authEnabled && !authRequired && authState.initialized}
						<!-- Sign in link for local mode users (optional auth) -->
						<a href="/login" class="sign-in-link">
							Sign in
						</a>
					{/if}

					<!-- Mobile menu button -->
					<button
						type="button"
						class="mobile-menu-btn"
						onclick={() => (mobileMenuOpen = !mobileMenuOpen)}
						aria-label="Toggle menu"
					>
						{#if mobileMenuOpen}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
							</svg>
						{:else}
							<svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M4 6h16M4 12h16M4 18h16" />
							</svg>
						{/if}
					</button>
				</div>
			</div>
		</div>

		<!-- Mobile menu -->
		{#if mobileMenuOpen}
			<div class="mobile-menu" transition:slide={{ duration: 150 }}>
				<div class="px-3 py-3 space-y-1">
					{#each navLinks as link}
						{@const active = isActive(link.href, $page.url.pathname)}
						<a
							href={link.href}
							onclick={closeMobileMenu}
							class="mobile-nav-link"
							class:active
						>
							{link.label}
						</a>
					{/each}
				</div>
			</div>
		{/if}
	</nav>

	<!-- Main content -->
	<main class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
		{#if !configInitialized}
			<!-- Loading config -->
			<div class="auth-loading">
				<div class="auth-loading-spinner"></div>
				<p>Loading...</p>
			</div>
		{:else if authRequired && !authState.initialized}
			<!-- Loading auth state -->
			<div class="auth-loading">
				<div class="auth-loading-spinner"></div>
				<p>Loading...</p>
			</div>
		{:else if authRequired && !authState.user && !isLoginPage}
			<!-- Redirecting to login -->
			<div class="auth-loading">
				<p>Redirecting to login...</p>
			</div>
		{:else}
			{@render children()}
		{/if}
	</main>
</div>

<style>
	/* Layout container */
	.layout-container {
		min-height: 100vh;
		background: var(--bg-deep);
	}

	/* Main navigation */
	.main-nav {
		position: sticky;
		top: 0;
		z-index: 50;
		backdrop-filter: blur(12px);
		background: rgba(15, 17, 21, 0.85);
		border-bottom: 1px solid var(--bg-hover);
	}

	/* Logo */
	.logo-icon {
		width: 2.25rem;
		height: 2.25rem;
		border-radius: 0.5rem;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--accent);
		transition: transform var(--transition);
	}

	.group:hover .logo-icon {
		transform: scale(1.05);
	}

	.logo-text {
		font-size: 1.125rem;
		font-weight: 600;
		letter-spacing: -0.025em;
		color: var(--text-primary);
	}

	.logo-accent {
		color: var(--accent);
	}

	/* Shared indicator text style */
	.indicator-text {
		font-size: 0.75rem;
		font-weight: 500;
		font-family: var(--font-mono);
		color: var(--text-secondary);
	}

	/* Ambient indicator */
	.ambient-indicator {
		display: none;
		align-items: center;
		gap: 0.75rem;
		padding: 0.375rem 0.75rem;
		border-radius: 9999px;
		background: var(--bg-elevated);
	}

	@media (min-width: 640px) {
		.ambient-indicator {
			display: flex;
		}
	}

	/* Heater indicator */
	.heater-indicator {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0.75rem;
		border-radius: 9999px;
		background: var(--bg-elevated);
	}

	.heater-indicator.heater-on {
		background: rgba(239, 68, 68, 0.1);
	}

	.heater-icon {
		font-size: 0.875rem;
		opacity: 0.4;
	}

	.heater-indicator.heater-on .heater-icon {
		opacity: 1;
	}

	.heater-text {
		font-size: 0.75rem;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.05em;
		color: var(--text-muted);
		display: none;
	}

	@media (min-width: 640px) {
		.heater-text {
			display: inline;
		}
	}

	.heater-indicator.heater-on .heater-text {
		color: var(--negative);
	}

	/* Connection indicator */
	.connection-indicator {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0.75rem;
		border-radius: 9999px;
		background: var(--bg-elevated);
	}

	.connection-dot {
		width: 0.5rem;
		height: 0.5rem;
		border-radius: 50%;
		background: var(--text-muted);
	}

	.connection-dot.connected {
		background: var(--positive);
	}

	.connection-text {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		display: none;
	}

	@media (min-width: 640px) {
		.connection-text {
			display: inline;
		}
	}

	/* Mobile menu button */
	.mobile-menu-btn {
		display: none;
		padding: 0.5rem;
		border-radius: 0.5rem;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		cursor: pointer;
		transition: color var(--transition);
	}

	.mobile-menu-btn:hover {
		color: var(--text-primary);
	}

	@media (max-width: 767px) {
		.mobile-menu-btn {
			display: flex;
		}
	}

	/* Mobile menu */
	.mobile-menu {
		display: none;
		background: var(--bg-primary);
		border-top: 1px solid var(--bg-hover);
	}

	@media (max-width: 767px) {
		.mobile-menu {
			display: block;
		}
	}

	/* Mobile nav link */
	.mobile-nav-link {
		display: block;
		padding: 0.75rem 1rem;
		border-radius: 0.5rem;
		font-size: 1rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		transition: color var(--transition), background var(--transition);
	}

	.mobile-nav-link:hover {
		color: var(--text-primary);
	}

	.mobile-nav-link.active {
		color: var(--text-primary);
		background: var(--bg-elevated);
	}

	/* Desktop nav link */
	.nav-link {
		position: relative;
		padding: 0.5rem 1rem;
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: transparent;
		border-radius: 0.375rem;
		transition: color var(--transition), background var(--transition);
	}

	.nav-link:hover {
		color: var(--text-primary);
	}

	.nav-link.active {
		color: var(--text-primary);
		background: var(--bg-elevated);
	}

	.nav-link.active::after {
		content: '';
		position: absolute;
		bottom: 0;
		left: 50%;
		transform: translateX(-50%);
		width: 1.5rem;
		height: 2px;
		background: var(--accent);
		border-radius: 1px;
	}

	/* Weather indicator */
	.weather-indicator-wrapper {
		position: relative;
	}

	.weather-indicator {
		display: flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.375rem 0.75rem;
		background: var(--bg-elevated);
		border: none;
		border-radius: 9999px;
		cursor: pointer;
		transition: background var(--transition);
	}

	.weather-indicator:hover {
		background: var(--bg-hover);
	}

	.weather-backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
	}

	.weather-dropdown {
		position: absolute;
		top: calc(100% + 0.5rem);
		right: 0;
		z-index: 50;
		min-width: 16rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
		overflow: hidden;
	}

	.weather-dropdown-header {
		padding: 0.75rem 1rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		border-bottom: 1px solid var(--border-subtle);
	}

	.weather-dropdown-days {
		padding: 0.5rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.weather-day {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.5rem 0.75rem;
		border-radius: 0.375rem;
		background: var(--bg-elevated);
	}

	.weather-day-name {
		flex: 0 0 4rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.weather-day-icon {
		font-size: 1.25rem;
	}

	.weather-day-temps {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.weather-temp-high {
		font-size: 0.875rem;
		font-weight: 500;
		font-family: var(--font-mono);
		color: var(--text-primary);
	}

	.weather-temp-low {
		font-size: 0.75rem;
		font-family: var(--font-mono);
		color: var(--text-muted);
	}

	/* User menu */
	.user-menu-wrapper {
		position: relative;
	}

	.user-menu-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 2rem;
		height: 2rem;
		border-radius: 9999px;
		background: var(--bg-elevated);
		border: none;
		color: var(--text-secondary);
		cursor: pointer;
		transition: background var(--transition), color var(--transition);
	}

	.user-menu-btn:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.user-menu-backdrop {
		position: fixed;
		inset: 0;
		z-index: 40;
	}

	.user-menu-dropdown {
		position: absolute;
		top: calc(100% + 0.5rem);
		right: 0;
		z-index: 50;
		min-width: 12rem;
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4);
		overflow: hidden;
	}

	.user-menu-email {
		padding: 0.75rem 1rem;
		font-size: 0.75rem;
		color: var(--text-muted);
		border-bottom: 1px solid var(--border-subtle);
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.user-menu-item {
		display: block;
		width: 100%;
		padding: 0.75rem 1rem;
		font-size: 0.875rem;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		text-align: left;
		cursor: pointer;
		transition: background var(--transition), color var(--transition);
	}

	.user-menu-item:hover {
		background: var(--bg-elevated);
		color: var(--text-primary);
	}

	.user-menu-item:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Sign in link for local mode */
	.sign-in-link {
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--accent);
		background: var(--bg-elevated);
		border-radius: 9999px;
		transition: background var(--transition), color var(--transition);
	}

	.sign-in-link:hover {
		background: var(--bg-hover);
		color: var(--accent-hover);
	}

	/* Auth loading state */
	.auth-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		min-height: 50vh;
		color: var(--text-muted);
	}

	.auth-loading-spinner {
		width: 2rem;
		height: 2rem;
		border: 2px solid var(--border-subtle);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: 1rem;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
