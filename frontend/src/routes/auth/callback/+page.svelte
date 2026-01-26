<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { supabase } from '$lib/supabase';

	let error = $state<string | null>(null);

	onMount(async () => {
		if (!supabase) {
			error = 'Auth not available';
			return;
		}

		// Supabase handles the OAuth callback automatically via the URL hash
		// We just need to wait for the session to be established
		const { data: { session }, error: authError } = await supabase.auth.getSession();

		if (authError) {
			error = authError.message;
			return;
		}

		if (session) {
			// Successfully authenticated, redirect to home
			goto('/');
		} else {
			// No session yet, might still be processing
			// Listen for auth state change
			const { data: { subscription } } = supabase.auth.onAuthStateChange((event, session) => {
				if (event === 'SIGNED_IN' && session) {
					subscription.unsubscribe();
					goto('/');
				}
			});

			// Timeout after 5 seconds
			setTimeout(() => {
				subscription.unsubscribe();
				if (!error) {
					error = 'Authentication timed out. Please try again.';
				}
			}, 5000);
		}
	});
</script>

<svelte:head>
	<title>Authenticating... - BrewSignal</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-zinc-900 px-4">
	<div class="text-center">
		{#if error}
			<div class="bg-red-500/10 border border-red-500/30 rounded-lg p-6 max-w-md">
				<p class="text-red-400 mb-4">{error}</p>
				<a href="/login" class="text-amber-500 hover:text-amber-400">
					Back to login
				</a>
			</div>
		{:else}
			<div class="flex flex-col items-center gap-4">
				<svg class="animate-spin w-8 h-8 text-amber-500" viewBox="0 0 24 24" fill="none">
					<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25" />
					<path fill="currentColor" class="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
				</svg>
				<p class="text-zinc-400">Completing authentication...</p>
			</div>
		{/if}
	</div>
</div>
