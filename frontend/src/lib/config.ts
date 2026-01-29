/**
 * BrewSignal Frontend Configuration
 *
 * Fetches configuration from the backend at runtime, enabling auth
 * in both local and cloud modes without build-time env vars.
 *
 * Uses Svelte writable stores for reactivity.
 */

import { writable, derived, get } from 'svelte/store';

// API URL - defaults to same origin for local, explicit URL for cloud
export const API_URL = import.meta.env.VITE_API_URL || '';

// Config state using Svelte writable stores
const deploymentModeStore = writable<'local' | 'cloud'>('local');
const authEnabledStore = writable(false);
const authRequiredStore = writable(false);
const supabaseUrlStore = writable<string | null>(null);
const supabaseAnonKeyStore = writable<string | null>(null);
const initializedStore = writable(false);

// Derived stores for convenience checks
const isCloudModeStore = derived(deploymentModeStore, $mode => $mode === 'cloud');
const isLocalModeStore = derived(deploymentModeStore, $mode => $mode === 'local');

// Reactive config object for Svelte components
// Uses getters that read from stores for reactivity
export const config = {
	get deploymentMode() { return get(deploymentModeStore); },
	get authEnabled() { return get(authEnabledStore); },
	get authRequired() { return get(authRequiredStore); },
	get supabaseUrl() { return get(supabaseUrlStore); },
	get supabaseAnonKey() { return get(supabaseAnonKeyStore); },
	get initialized() { return get(initializedStore); },

	// Convenience checks
	get isCloudMode() { return get(isCloudModeStore); },
	get isLocalMode() { return get(isLocalModeStore); },

	// Feature flags
	get multiTenant() { return get(isCloudModeStore); },
	get showDeviceSetup() { return get(isLocalModeStore); },
	get directBLEEnabled() { return get(isLocalModeStore); },
	get gatewayMode() { return get(isCloudModeStore); },
};

// Export stores for reactive subscriptions in components
export const configStores = {
	deploymentMode: deploymentModeStore,
	authEnabled: authEnabledStore,
	authRequired: authRequiredStore,
	supabaseUrl: supabaseUrlStore,
	supabaseAnonKey: supabaseAnonKeyStore,
	initialized: initializedStore,
	isCloudMode: isCloudModeStore,
	isLocalMode: isLocalModeStore,
};

// Callbacks for when config is loaded
const configLoadCallbacks: Array<() => void> = [];

/**
 * Register a callback to be called when config is loaded
 */
export function onConfigLoaded(callback: () => void): void {
	if (get(initializedStore)) {
		callback();
	} else {
		configLoadCallbacks.push(callback);
	}
}

/**
 * Fetch app configuration from the backend.
 * Should be called once during app initialization.
 */
export async function fetchAppConfig(): Promise<void> {
	if (get(initializedStore)) return;

	try {
		const response = await fetch(`${API_URL}/api/config/app`);
		if (!response.ok) {
			console.error('Failed to fetch app config:', response.status);
			// Fall back to defaults (local mode, no auth)
			initializedStore.set(true);
			return;
		}

		const data = await response.json();

		// Update stores
		deploymentModeStore.set(data.deployment_mode || 'local');
		authEnabledStore.set(data.auth_enabled || false);
		authRequiredStore.set(data.auth_required || false);
		supabaseUrlStore.set(data.supabase_url || null);
		supabaseAnonKeyStore.set(data.supabase_anon_key || null);
		initializedStore.set(true);

		// Notify callbacks
		configLoadCallbacks.forEach(cb => cb());
		configLoadCallbacks.length = 0;

	} catch (error) {
		console.error('Failed to fetch app config:', error);
		// Fall back to defaults (local mode, no auth)
		initializedStore.set(true);
	}
}

// Legacy exports for backward compatibility during migration
// These will use empty strings until config is fetched
export const SUPABASE_URL = '';
export const SUPABASE_ANON_KEY = '';
export const supabaseConfigured = false;
export const isCloudMode = false;
export const isLocalMode = true;
