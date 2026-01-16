<script lang="ts">
	import type { RecipeResponse, YeastStrainResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { ABV_MULTIPLIER } from '$lib/constants';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		recipe: RecipeResponse;
		yeastStrain?: YeastStrainResponse | null;
	}

	let { recipe, yeastStrain }: Props = $props();

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
	{#if yeastStrain || recipe.yeast_name}
		<div class="yeast-section">
			{#if yeastStrain}
				<div class="yeast-row actual">
					<span class="yeast-label">Yeast</span>
					<span class="yeast-value">{yeastStrain.name}</span>
					{#if yeastStrain.producer}
						<span class="yeast-producer">({yeastStrain.producer})</span>
					{/if}
					{#if yeastStrain.temp_low && yeastStrain.temp_high}
						<span class="yeast-temp">{yeastStrain.temp_low.toFixed(0)}-{yeastStrain.temp_high.toFixed(0)}°C</span>
					{/if}
				</div>
				{#if recipe.yeast_name}
					<div class="yeast-row recipe">
						<span class="yeast-label">Recipe</span>
						<span class="yeast-value muted">{recipe.yeast_name}</span>
					</div>
				{/if}
			{:else if recipe.yeast_name}
				<div class="yeast-row">
					<span class="yeast-label">Yeast</span>
					<span class="yeast-value">{recipe.yeast_name}</span>
				</div>
			{/if}
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

	.yeast-section {
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--border-subtle);
	}

	.yeast-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.375rem;
	}

	.yeast-label {
		font-size: 0.625rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		min-width: 2.5rem;
	}

	.yeast-value {
		font-size: 0.8125rem;
		color: var(--text-secondary);
	}

	.yeast-value.muted {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.yeast-producer {
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	.yeast-temp {
		font-size: 0.6875rem;
		font-family: var(--font-mono);
		color: var(--text-muted);
		padding: 0.125rem 0.375rem;
		background: var(--bg-elevated);
		border-radius: 0.25rem;
	}
</style>
