/**
 * Auth Store for BrewSignal
 *
 * Manages authentication state using Svelte 5 runes.
 * Auth is available in both local and cloud modes when Supabase is configured.
 * - Cloud mode: Auth is required
 * - Local mode: Auth is optional but enables data claiming and multi-tenant features
 */

import type { User, Session } from '@supabase/supabase-js';
import { getSupabase } from '$lib/supabase';
import { config } from '$lib/config';

// Auth state using Svelte 5 runes
let user = $state<User | null>(null);
let session = $state<Session | null>(null);
let loading = $state(true);
let initialized = $state(false);

/**
 * Initialize auth state and set up listener.
 * Should be called after app config is fetched.
 */
export async function initAuth() {
	if (initialized) return;

	// Get the Supabase client (will be null if auth not configured)
	const supabase = getSupabase();

	// If no Supabase client, mark as initialized (no auth available)
	if (!supabase) {
		loading = false;
		initialized = true;
		return;
	}

	// Get initial session
	const { data: { session: initialSession } } = await supabase.auth.getSession();
	session = initialSession;
	user = initialSession?.user ?? null;
	loading = false;
	initialized = true;

	// Listen for auth changes
	supabase.auth.onAuthStateChange((_event, newSession) => {
		session = newSession;
		user = newSession?.user ?? null;
	});
}

/**
 * Check if user is authenticated
 * In local mode with auth not required, returns true even without user
 * In cloud mode (auth required), requires actual user session
 */
export function isAuthenticated(): boolean {
	if (!config.authRequired) return true;
	return !!user;
}

/**
 * Get current auth state (reactive)
 */
export function getAuthState() {
	return {
		get user() { return user; },
		get session() { return session; },
		get loading() { return loading; },
		get initialized() { return initialized; },
		get isAuthenticated() { return isAuthenticated(); },
	};
}

// Export reactive state for direct use in components
export const authState = {
	get user() { return user; },
	get session() { return session; },
	get loading() { return loading; },
	get initialized() { return initialized; },
	get isAuthenticated() { return isAuthenticated(); },
};
