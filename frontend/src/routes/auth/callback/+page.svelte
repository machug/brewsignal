<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { getSupabase } from '$lib/supabase';
	import { fetchAppConfig, config } from '$lib/config';

	let error = $state<string | null>(null);

	onMount(async () => {
		// Ensure app config is loaded (provides Supabase credentials)
		await fetchAppConfig();

		const supabase = getSupabase();
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

<div class="auth-page">
	<div class="center">
		{#if error}
			<div class="notice" role="alert">
				<p class="msg-error">{error}</p>
				<a href="/login" class="back">Back to login</a>
			</div>
		{:else}
			<div class="busy" role="status">
				<svg class="spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
					<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="o25" />
					<path fill="currentColor" class="o75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
				</svg>
				<p>Completing authentication&hellip;</p>
			</div>
		{/if}
	</div>
</div>

<style>
	.auth-page {
		min-height: 100vh;
		min-height: 100dvh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: var(--space-md);
		background: var(--bg-canvas);
		color: var(--ink-secondary);
	}
	.center {
		text-align: center;
	}
	.notice {
		max-width: 22rem;
		padding: var(--space-md);
		border: 1px solid color-mix(in oklch, var(--status-danger) 60%, transparent);
		border-radius: 4px;
	}
	.msg-error {
		color: var(--status-danger);
		margin-bottom: var(--space-sm);
	}
	.back {
		display: inline-flex;
		align-items: center;
		min-height: 44px;
		color: var(--accent);
		font-family: var(--font-display);
		font-weight: 600;
	}
	.back:hover {
		color: var(--accent-hover);
	}
	.busy {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-sm);
	}
	.spin {
		width: 2rem;
		height: 2rem;
		color: var(--accent);
		animation: spin 0.9s linear infinite;
	}
	.o25 {
		opacity: 0.25;
	}
	.o75 {
		opacity: 0.75;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
