<script lang="ts">
	import { goto } from '$app/navigation';
	import { signInWithEmail, signUpWithEmail } from '$lib/supabase';
	import { authState } from '$lib/stores/auth.svelte';
	import { isCloudMode } from '$lib/config';

	let email = $state('');
	let password = $state('');
	let isSignUp = $state(false);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let message = $state<string | null>(null);

	// Redirect if already authenticated or in local mode
	$effect(() => {
		if (!isCloudMode || authState.isAuthenticated) {
			goto('/');
		}
	});

	async function handleSubmit(e: Event) {
		e.preventDefault();
		loading = true;
		error = null;
		message = null;

		try {
			if (isSignUp) {
				await signUpWithEmail(email, password);
				message = 'Check your email for a confirmation link!';
				isSignUp = false;
			} else {
				await signInWithEmail(email, password);
				goto('/');
			}
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred';
		} finally {
			loading = false;
		}
	}

	function toggleMode() {
		isSignUp = !isSignUp;
		error = null;
		message = null;
	}
</script>

<svelte:head>
	<title>{isSignUp ? 'Sign Up' : 'Sign In'} - BrewSignal</title>
</svelte:head>

<div class="min-h-screen flex items-center justify-center bg-zinc-900 px-4">
	<div class="max-w-md w-full">
		<!-- Logo -->
		<div class="text-center mb-8">
			<div class="flex items-center justify-center gap-3 mb-2">
				<img src="/icon.svg" alt="BrewSignal" class="w-10 h-10" />
				<h1 class="text-3xl font-bold text-white">BrewSignal</h1>
			</div>
			<p class="text-zinc-400">Fermentation monitoring made simple</p>
		</div>

		<!-- Auth Card -->
		<div class="bg-zinc-800 rounded-xl p-8 shadow-xl border border-zinc-700">
			<h2 class="text-xl font-semibold text-white mb-6">
				{isSignUp ? 'Create an account' : 'Welcome back'}
			</h2>

			{#if error}
				<div class="mb-4 p-3 bg-red-500/10 border border-red-500/30 rounded-lg text-red-400 text-sm">
					{error}
				</div>
			{/if}

			{#if message}
				<div class="mb-4 p-3 bg-green-500/10 border border-green-500/30 rounded-lg text-green-400 text-sm">
					{message}
				</div>
			{/if}

			<form onsubmit={handleSubmit} class="space-y-4">
				<div>
					<label for="email" class="block text-sm font-medium text-zinc-300 mb-1">
						Email
					</label>
					<input
						type="email"
						id="email"
						bind:value={email}
						required
						class="w-full px-4 py-2.5 bg-zinc-900 border border-zinc-600 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
						placeholder="you@example.com"
					/>
				</div>

				<div>
					<label for="password" class="block text-sm font-medium text-zinc-300 mb-1">
						Password
					</label>
					<input
						type="password"
						id="password"
						bind:value={password}
						required
						minlength="6"
						class="w-full px-4 py-2.5 bg-zinc-900 border border-zinc-600 rounded-lg text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent"
						placeholder="••••••••"
					/>
				</div>

				<button
					type="submit"
					disabled={loading}
					class="w-full py-2.5 px-4 bg-amber-600 hover:bg-amber-500 disabled:bg-amber-600/50 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
				>
					{#if loading}
						<svg class="animate-spin w-5 h-5" viewBox="0 0 24 24" fill="none">
							<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="opacity-25" />
							<path fill="currentColor" class="opacity-75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
					{/if}
					{isSignUp ? 'Create Account' : 'Sign In'}
				</button>
			</form>

			<div class="mt-6 text-center">
				<button
					type="button"
					onclick={toggleMode}
					class="text-amber-500 hover:text-amber-400 text-sm"
				>
					{isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
				</button>
			</div>
		</div>
	</div>
</div>
