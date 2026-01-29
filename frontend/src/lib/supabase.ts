/**
 * Supabase Client for BrewSignal
 *
 * Handles authentication and database access.
 * Client is lazily initialized after app config is fetched from backend.
 */

import { createBrowserClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import { config } from '$lib/config';

// Lazily initialized Supabase client
let _supabase: SupabaseClient | null = null;

/**
 * Get the Supabase client (lazily initialized)
 */
export function getSupabase(): SupabaseClient | null {
	// Initialize on first access if config is ready
	if (!_supabase && config.authEnabled && config.supabaseUrl && config.supabaseAnonKey) {
		_supabase = createBrowserClient(config.supabaseUrl, config.supabaseAnonKey);
	}
	return _supabase;
}

// Export for backward compatibility (will be null until config loaded)
export const supabase = {
	get client() { return getSupabase(); },
	get auth() { return getSupabase()?.auth; },
};

/**
 * Get the current session's access token for API calls
 */
export async function getAccessToken(): Promise<string | null> {
	const client = getSupabase();
	if (!client) return null;

	const { data: { session } } = await client.auth.getSession();
	return session?.access_token ?? null;
}

/**
 * Sign in with email and password
 */
export async function signInWithEmail(email: string, password: string) {
	const client = getSupabase();
	if (!client) throw new Error('Auth not available');

	const { data, error } = await client.auth.signInWithPassword({
		email,
		password,
	});

	if (error) throw error;
	return data;
}

/**
 * Sign up with email and password
 */
export async function signUpWithEmail(email: string, password: string) {
	const client = getSupabase();
	if (!client) throw new Error('Auth not available');

	const { data, error } = await client.auth.signUp({
		email,
		password,
	});

	if (error) throw error;
	return data;
}

/**
 * Sign in with Google OAuth
 */
export async function signInWithGoogle() {
	const client = getSupabase();
	if (!client) throw new Error('Auth not available');

	const { data, error } = await client.auth.signInWithOAuth({
		provider: 'google',
		options: {
			redirectTo: `${window.location.origin}/auth/callback`,
		},
	});

	if (error) throw error;
	return data;
}

/**
 * Sign in with Magic Link (passwordless email)
 */
export async function signInWithMagicLink(email: string) {
	const client = getSupabase();
	if (!client) throw new Error('Auth not available');

	const { data, error } = await client.auth.signInWithOtp({
		email,
		options: {
			emailRedirectTo: `${window.location.origin}/auth/callback`,
		},
	});

	if (error) throw error;
	return data;
}

/**
 * Sign out the current user
 */
export async function signOut() {
	const client = getSupabase();
	if (!client) return;

	const { error } = await client.auth.signOut();
	if (error) throw error;
}

/**
 * Get the current user
 */
export async function getCurrentUser() {
	const client = getSupabase();
	if (!client) return null;

	const { data: { user } } = await client.auth.getUser();
	return user;
}
