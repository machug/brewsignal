<script lang="ts">
	import type { RecipeResponse, YeastStrainResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { ABV_MULTIPLIER } from '$lib/constants';

	interface Props {
		recipe: RecipeResponse;
		yeastStrain?: YeastStrainResponse | null;
	}

	let { recipe, yeastStrain }: Props = $props();

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	let calculatedABV = $derived.by(() => {
		if (recipe.abv != null) return recipe.abv;
		if (recipe.og && recipe.fg) {
			return (recipe.og - recipe.fg) * ABV_MULTIPLIER;
		}
		return null;
	});

	let yeastDisplay = $derived.by(() => {
		if (yeastStrain) {
			let text = yeastStrain.name;
			if (yeastStrain.producer) text += ` (${yeastStrain.producer})`;
			if (yeastStrain.temp_low && yeastStrain.temp_high) {
				text += ` ${yeastStrain.temp_low.toFixed(0)}-${yeastStrain.temp_high.toFixed(0)}°C`;
			}
			return text;
		}
		return recipe.yeast_name || null;
	});
</script>

<div class="recipe-strip">
	<span class="item"><span class="lbl">OG</span> <span class="val">{formatSG(recipe.og)}</span></span>
	<span class="item"><span class="lbl">FG</span> <span class="val">{formatSG(recipe.fg)}</span></span>
	<span class="item"><span class="lbl">ABV</span> <span class="val">{calculatedABV != null ? `${calculatedABV.toFixed(1)}%` : '--'}</span></span>
	{#if yeastDisplay}
		<span class="sep"></span>
		<span class="item yeast">{yeastDisplay}</span>
	{/if}
	{#if recipe.name}
		<span class="sep"></span>
		<span class="item recipe-name">{recipe.name}</span>
	{/if}
</div>

<style>
	.recipe-strip {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: 0.25rem 0.75rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.item {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		white-space: nowrap;
	}

	.lbl {
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.val {
		font-family: var(--font-mono);
	}

	.sep {
		width: 1px;
		height: 0.75rem;
		background: var(--border-subtle);
	}

	.yeast {
		color: var(--text-secondary);
	}

	.recipe-name {
		color: var(--text-muted);
		font-style: italic;
	}
</style>
