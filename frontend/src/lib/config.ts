/**
 * BrewSignal Frontend Configuration
 *
 * Fetches configuration from the backend at runtime, enabling auth
 * in both local and cloud modes without build-time env vars.
 */

// API URL - defaults to same origin for local, explicit URL for cloud
export const API_URL = import.meta.env.VITE_API_URL || '';

// App config state - populated by fetchAppConfig()
interface AppConfig {
	deploymentMode: 'local' | 'cloud';
	authEnabled: boolean;
	authRequired: boolean;
	supabaseUrl: string | null;
	supabaseAnonKey: string | null;
	initialized: boolean;
}

let appConfig: AppConfig = {
	deploymentMode: 'local',
	authEnabled: false,
	authRequired: false,
	supabaseUrl: null,
	supabaseAnonKey: null,
	initialized: false,
};

// Reactive config for Svelte components
export const config = {
	get deploymentMode() { return appConfig.deploymentMode; },
	get authEnabled() { return appConfig.authEnabled; },
	get authRequired() { return appConfig.authRequired; },
	get supabaseUrl() { return appConfig.supabaseUrl; },
	get supabaseAnonKey() { return appConfig.supabaseAnonKey; },
	get initialized() { return appConfig.initialized; },

	// Convenience checks
	get isCloudMode() { return appConfig.deploymentMode === 'cloud'; },
	get isLocalMode() { return appConfig.deploymentMode === 'local'; },

	// Feature flags
	get multiTenant() { return appConfig.deploymentMode === 'cloud'; },
	get showDeviceSetup() { return appConfig.deploymentMode === 'local'; },
	get directBLEEnabled() { return appConfig.deploymentMode === 'local'; },
	get gatewayMode() { return appConfig.deploymentMode === 'cloud'; },
};

// Callbacks for when config is loaded
const configLoadCallbacks: Array<() => void> = [];

/**
 * Register a callback to be called when config is loaded
 */
export function onConfigLoaded(callback: () => void): void {
	if (appConfig.initialized) {
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
	if (appConfig.initialized) return;

	try {
		const response = await fetch(`${API_URL}/api/config/app`);
		if (!response.ok) {
			console.error('Failed to fetch app config:', response.status);
			// Fall back to defaults (local mode, no auth)
			appConfig.initialized = true;
			return;
		}

		const data = await response.json();
		appConfig = {
			deploymentMode: data.deployment_mode || 'local',
			authEnabled: data.auth_enabled || false,
			authRequired: data.auth_required || false,
			supabaseUrl: data.supabase_url || null,
			supabaseAnonKey: data.supabase_anon_key || null,
			initialized: true,
		};

		// Notify callbacks
		configLoadCallbacks.forEach(cb => cb());
		configLoadCallbacks.length = 0;

	} catch (error) {
		console.error('Failed to fetch app config:', error);
		// Fall back to defaults (local mode, no auth)
		appConfig.initialized = true;
	}
}

// Legacy exports for backward compatibility during migration
// These will use empty strings until config is fetched
export const SUPABASE_URL = '';
export const SUPABASE_ANON_KEY = '';
export const supabaseConfigured = false;
export const isCloudMode = false;
export const isLocalMode = true;
