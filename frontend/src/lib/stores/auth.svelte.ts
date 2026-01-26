/**
 * Auth Store for BrewSignal
 *
 * Manages authentication state using Svelte 5 runes.
 * In local mode, user is always considered authenticated.
 */

import type { User, Session } from '@supabase/supabase-js';
import { supabase } from '$lib/supabase';
import { isCloudMode } from '$lib/config';

// Auth state using Svelte 5 runes
let user = $state<User | null>(null);
let session = $state<Session | null>(null);
let loading = $state(true);
let initialized = $state(false);

/**
 * Initialize auth state and set up listener
 */
export async function initAuth() {
	if (initialized) return;

	// In local mode, no auth needed
	if (!isCloudMode || !supabase) {
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
 * In local mode, always returns true
 */
export function isAuthenticated(): boolean {
	if (!isCloudMode) return true;
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
