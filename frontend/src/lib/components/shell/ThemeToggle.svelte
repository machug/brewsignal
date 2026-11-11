<script lang="ts">
	import { themeState, setTheme } from '$lib/stores/theme.svelte';
</script>

<button
	type="button"
	class="theme-toggle"
	aria-label="Switch colour theme"
	onclick={() => setTheme(themeState.theme === 'dark' ? 'light' : 'dark')}
>
	<svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.4" aria-hidden="true">
		<circle cx="8" cy="8" r="3.5" />
		<path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4" />
	</svg>
</button>

<style>
	.theme-toggle {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		border: 1px solid var(--rule-hairline);
		border-radius: 4px;
		background: var(--bg-surface);
		color: var(--ink-secondary);
		cursor: pointer;
		transition: border-color 150ms var(--ease-out-quart), color 150ms var(--ease-out-quart);
	}
	.theme-toggle:hover {
		border-color: var(--rule-strong);
		color: var(--ink-primary);
	}
</style>
