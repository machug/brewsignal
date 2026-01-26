<script lang="ts">
	import { goto } from '$app/navigation';
	import { signInWithEmail, signUpWithEmail, signInWithGoogle, signInWithMagicLink } from '$lib/supabase';
	import { authState } from '$lib/stores/auth.svelte';
	import { isCloudMode } from '$lib/config';

	let email = $state('');
	let password = $state('');
	let isSignUp = $state(false);
	let isMagicLink = $state(false);
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
			if (isMagicLink) {
				await signInWithMagicLink(email);
				message = 'Check your email for a magic link!';
			} else if (isSignUp) {
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

	async function handleGoogleSignIn() {
		loading = true;
		error = null;
		try {
			await signInWithGoogle();
			// Redirects to Google, then back to /auth/callback
		} catch (err) {
			error = err instanceof Error ? err.message : 'An error occurred';
			loading = false;
		}
	}

	function toggleMode() {
		isSignUp = !isSignUp;
		isMagicLink = false;
		error = null;
		message = null;
	}

	function toggleMagicLink() {
		isMagicLink = !isMagicLink;
		isSignUp = false;
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
				{isSignUp ? 'Create an account' : isMagicLink ? 'Sign in with Magic Link' : 'Welcome back'}
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

			<!-- Google Sign In -->
			<button
				type="button"
				onclick={handleGoogleSignIn}
				disabled={loading}
				class="w-full py-2.5 px-4 bg-white hover:bg-zinc-100 disabled:bg-zinc-300 text-zinc-800 font-medium rounded-lg transition-colors flex items-center justify-center gap-3 mb-4"
			>
				<svg class="w-5 h-5" viewBox="0 0 24 24">
					<path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
					<path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
					<path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
					<path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
				</svg>
				Continue with Google
			</button>

			<div class="relative mb-4">
				<div class="absolute inset-0 flex items-center">
					<div class="w-full border-t border-zinc-600"></div>
				</div>
				<div class="relative flex justify-center text-sm">
					<span class="px-2 bg-zinc-800 text-zinc-400">or</span>
				</div>
			</div>

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

				{#if !isMagicLink}
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
				{/if}

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
					{isMagicLink ? 'Send Magic Link' : isSignUp ? 'Create Account' : 'Sign In'}
				</button>
			</form>

			<div class="mt-6 space-y-2 text-center">
				<button
					type="button"
					onclick={toggleMagicLink}
					class="text-zinc-400 hover:text-zinc-300 text-sm block w-full"
				>
					{isMagicLink ? 'Sign in with password instead' : 'Sign in with Magic Link (no password)'}
				</button>
				{#if !isMagicLink}
					<button
						type="button"
						onclick={toggleMode}
						class="text-amber-500 hover:text-amber-400 text-sm block w-full"
					>
						{isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
					</button>
				{/if}
			</div>
		</div>
	</div>
</div>
