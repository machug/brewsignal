<script lang="ts">
	import type { Snippet } from 'svelte';
	// TODO(logo): a new logo is being designed separately. Pass it via the `mark`
	// snippet (20x20 box); until then the slot stays empty.
	let { mark }: { mark?: Snippet } = $props();
</script>

<a href="/" class="brand" aria-label="BrewSignal home">
	<span class="brand-mark" aria-hidden="true">{#if mark}{@render mark()}{/if}</span>
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
		width: 20px;
		height: 20px;
		flex-shrink: 0;
		display: inline-flex;
	}
	.brand-mark:empty {
		display: none; /* no gap reserved until a mark exists */
	}
	.brand-word {
		font-family: var(--font-display);
		font-weight: 700;
		font-stretch: 95%;
		font-variation-settings: 'wdth' 95;
		font-size: var(--text-base);
		letter-spacing: -0.01em;
	}
</style>
