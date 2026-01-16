<script lang="ts">
	import type { RecipeResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { ABV_MULTIPLIER } from '$lib/constants';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		recipe: RecipeResponse;
	}

	let { recipe }: Props = $props();

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	// Calculate ABV from recipe targets if not provided
	let calculatedABV = $derived.by(() => {
		if (recipe.abv != null) return recipe.abv; // Already stored as percentage
		if (recipe.og && recipe.fg) {
			return (recipe.og - recipe.fg) * ABV_MULTIPLIER;
		}
		return null;
	});
</script>

<BatchCard title="Recipe Targets" compact>
	<div class="targets-row">
		<div class="target">
			<span class="target-label">OG</span>
			<span class="target-value">{formatSG(recipe.og)}</span>
		</div>
		<div class="target">
			<span class="target-label">FG</span>
			<span class="target-value">{formatSG(recipe.fg)}</span>
		</div>
		<div class="target">
			<span class="target-label">ABV</span>
			<span class="target-value">
				{calculatedABV != null ? `${calculatedABV.toFixed(1)}%` : '--'}
			</span>
		</div>
	</div>
	{#if recipe.yeast_name}
		<div class="yeast-row">
			<span class="yeast-label">Yeast</span>
			<span class="yeast-value">{recipe.yeast_name}</span>
		</div>
	{/if}
</BatchCard>

<style>
	.targets-row {
		display: flex;
		gap: 1.5rem;
	}

	.target {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.target-label {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.target-value {
		font-family: var(--font-mono);
		font-size: 0.9375rem;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.yeast-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--border-subtle);
	}

	.yeast-label {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.yeast-value {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}
</style>
