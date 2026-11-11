<script lang="ts">
	import { goto } from '$app/navigation';
	import { signInWithEmail, signUpWithEmail, signInWithGoogle, signInWithMagicLink } from '$lib/supabase';
	import { authState } from '$lib/stores/auth.svelte';
	import { config } from '$lib/config';
	import Mark from '$lib/components/shell/Mark.svelte';

	let email = $state('');
	let password = $state('');
	let isSignUp = $state(false);
	let isMagicLink = $state(false);
	let loading = $state(false);
	let error = $state<string | null>(null);
	let message = $state<string | null>(null);

	// Redirect if auth is not available or already authenticated
	$effect(() => {
		// Wait for config to be initialized
		if (!config.initialized) return;

		// If auth not enabled, can't login
		if (!config.authEnabled) {
			goto('/');
			return;
		}

		// If already authenticated with a user, redirect home
		if (authState.user) {
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

<div class="auth-page">
	<div class="auth-wrap">
		<!-- Logo -->
		<div class="brand">
			<div class="brand-row">
				<span class="brand-mark"><Mark size={32} /></span>
				<h1 class="brand-name">BrewSignal</h1>
			</div>
			<p class="brand-tag">Sign in to your brewery</p>
		</div>

		<!-- Auth Card -->
		<div class="auth-panel">
			<h2 class="auth-title">
				{isSignUp ? 'Create an account' : isMagicLink ? 'Sign in with Magic Link' : 'Welcome back'}
			</h2>

			{#if error}
				<div class="notice notice-error" role="alert">
					{error}
				</div>
			{/if}

			{#if message}
				<div class="notice notice-ok" role="status">
					{message}
				</div>
			{/if}

			<!-- Google Sign In -->
			<button
				type="button"
				onclick={handleGoogleSignIn}
				disabled={loading}
				class="btn btn-secondary google-btn"
			>
				<svg class="google-g" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
					<path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
					<path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
					<path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
					<path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
				</svg>
				Continue with Google
			</button>

			<div class="or-rule"><span>or</span></div>

			<form onsubmit={handleSubmit} class="auth-form">
				<div>
					<label for="email" class="field-label">
						Email
					</label>
					<input
						type="email"
						id="email"
						bind:value={email}
						required
						class="field"
						placeholder="you@example.com"
					/>
				</div>

				{#if !isMagicLink}
					<div>
						<label for="password" class="field-label">
							Password
						</label>
						<input
							type="password"
							id="password"
							bind:value={password}
							required
							minlength="6"
							class="field"
							placeholder="••••••••"
						/>
					</div>
				{/if}

				<button
					type="submit"
					disabled={loading}
					class="btn btn-primary"
				>
					{#if loading}
						<svg class="spin" aria-hidden="true" viewBox="0 0 24 24" fill="none">
							<circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" class="o25" />
							<path fill="currentColor" class="o75" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
						</svg>
					{/if}
					{isMagicLink ? 'Send Magic Link' : isSignUp ? 'Create Account' : 'Sign In'}
				</button>
			</form>

			<div class="alt-actions">
				<button
					type="button"
					onclick={toggleMagicLink}
					class="link-btn"
				>
					{isMagicLink ? 'Sign in with password instead' : 'Sign in with Magic Link (no password)'}
				</button>
				{#if !isMagicLink}
					<button
						type="button"
						onclick={toggleMode}
						class="link-btn link-accent"
					>
						{isSignUp ? 'Already have an account? Sign in' : "Don't have an account? Sign up"}
					</button>
				{/if}
			</div>
		</div>
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
		color: var(--ink-primary);
	}
	.auth-wrap {
		width: 100%;
		max-width: 22rem;
	}
	.brand {
		text-align: center;
		margin-bottom: var(--space-lg);
	}
	.brand-row {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
	}
	.brand-mark {
		display: inline-flex;
		color: var(--ink-primary);
	}
	.brand-name {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 700;
		letter-spacing: -0.02em;
	}
	.brand-tag {
		margin-top: var(--space-2xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.auth-panel {
		padding: var(--space-lg);
		background: var(--bg-surface);
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
	}
	.auth-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		margin-bottom: var(--space-md);
	}
	.notice {
		margin-bottom: var(--space-md);
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid;
		border-radius: 4px;
		font-size: var(--text-sm);
	}
	.notice-error {
		color: var(--status-danger);
		border-color: color-mix(in oklch, var(--status-danger) 60%, transparent);
	}
	.notice-ok {
		color: var(--status-steady);
		border-color: color-mix(in oklch, var(--status-steady) 60%, transparent);
	}
	.btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
	.btn-primary {
		color: var(--accent-ink);
		background: var(--accent);
	}
	.btn-primary:hover:not(:disabled) {
		background: var(--accent-hover);
	}
	.btn-secondary {
		color: var(--ink-primary);
		background: var(--bg-subtle);
		border: 1px solid var(--rule-strong);
	}
	.btn-secondary:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent-rule);
	}
	.google-btn {
		margin-bottom: var(--space-md);
	}
	.google-g {
		width: 1.125rem;
		height: 1.125rem;
	}
	.or-rule {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.or-rule::before,
	.or-rule::after {
		content: '';
		flex: 1;
		border-top: 1px solid var(--rule-hairline);
	}
	.auth-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}
	.field-label {
		display: block;
		margin-bottom: var(--space-2xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.field {
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-size: var(--text-base);
		color: var(--ink-primary);
		background: var(--bg-canvas);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}
	.field::placeholder {
		color: var(--ink-muted);
	}
	.field:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}
	.alt-actions {
		display: flex;
		flex-direction: column;
		margin-top: var(--space-md);
		text-align: center;
	}
	.link-btn {
		min-height: 44px;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		cursor: pointer;
	}
	.link-btn:hover {
		color: var(--ink-primary);
	}
	.link-accent {
		color: var(--accent);
	}
	.link-accent:hover {
		color: var(--accent-hover);
	}
	.spin {
		width: 1.125rem;
		height: 1.125rem;
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
	@media (prefers-reduced-motion: reduce) {
		.spin {
			animation-duration: 3s;
		}
	}
</style>
