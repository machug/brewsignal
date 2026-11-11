<script lang="ts">
	import Mark from './Mark.svelte';
</script>

<a href="/" class="brand" aria-label="BrewSignal home">
	<span class="brand-mark"><Mark size={22} /></span>
	<span class="brand-word">BrewSignal</span>
</a>

<style>
	.brand {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		color: var(--ink-primary);
		text-decoration: none;
		min-height: 44px;
	}
	.brand-mark {
		display: inline-flex;
		flex-shrink: 0;
	}
	/* Wordmark per the chosen lockup: Archivo wdth 100, wght 600, -0.018em */
	.brand-word {
		font-family: var(--font-display);
		font-weight: 600;
		font-variation-settings: 'wdth' 100;
		font-size: 1.0625rem;
		letter-spacing: -0.018em;
	}
</style>
