/**
 * Supabase Client for BrewSignal
 *
 * Handles authentication and database access for cloud mode.
 */

import { createBrowserClient } from '@supabase/ssr';
import { SUPABASE_URL, SUPABASE_ANON_KEY, isCloudMode } from './config';

// Create Supabase client (only functional in cloud mode)
export const supabase = isCloudMode && SUPABASE_URL && SUPABASE_ANON_KEY
	? createBrowserClient(SUPABASE_URL, SUPABASE_ANON_KEY)
	: null;

// Type for the Supabase client
export type SupabaseClient = typeof supabase;

/**
 * Get the current session's access token for API calls
 */
export async function getAccessToken(): Promise<string | null> {
	if (!supabase) return null;

	const { data: { session } } = await supabase.auth.getSession();
	return session?.access_token ?? null;
}

/**
 * Sign in with email and password
 */
export async function signInWithEmail(email: string, password: string) {
	if (!supabase) throw new Error('Auth not available in local mode');

	const { data, error } = await supabase.auth.signInWithPassword({
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
	if (!supabase) throw new Error('Auth not available in local mode');

	const { data, error } = await supabase.auth.signUp({
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
	if (!supabase) throw new Error('Auth not available in local mode');

	const { data, error } = await supabase.auth.signInWithOAuth({
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
	if (!supabase) throw new Error('Auth not available in local mode');

	const { data, error } = await supabase.auth.signInWithOtp({
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
	if (!supabase) return;

	const { error } = await supabase.auth.signOut();
	if (error) throw error;
}

/**
 * Get the current user
 */
export async function getCurrentUser() {
	if (!supabase) return null;

	const { data: { user } } = await supabase.auth.getUser();
	return user;
}
