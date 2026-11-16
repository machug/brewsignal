<script lang="ts">
	import type { RecipeResponse, YeastStrainResponse } from '$lib/api';
	import { formatGravity } from '$lib/stores/config.svelte';
	import type { StatValues } from '$lib/recipeStats';

	interface Props {
		recipe: RecipeResponse;
		// The batch's target numbers (see batchExpected in $lib/recipeStats)
		expected: StatValues;
		yeastStrain?: YeastStrainResponse | null;
	}

	let { recipe, expected, yeastStrain }: Props = $props();

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	let yeastDisplay = $derived.by(() => {
		if (yeastStrain) {
			let text = yeastStrain.name;
			if (yeastStrain.producer) text += ` (${yeastStrain.producer})`;
			if (yeastStrain.temp_low && yeastStrain.temp_high) {
				text += ` ${yeastStrain.temp_low.toFixed(0)}\u2013${yeastStrain.temp_high.toFixed(0)}\u2009°C`;
			}
			return text;
		}
		return recipe.yeast_name || null;
	});
</script>

<div class="recipe-strip">
	<span class="item"><span class="lbl">Target OG</span> <span class="val">{formatSG(expected.og)}</span></span>
	<span class="item"><span class="lbl">Target FG</span> <span class="val">{formatSG(expected.fg)}</span></span>
	<span class="item"><span class="lbl">Target ABV</span> <span class="val">{expected.abv != null ? `${expected.abv.toFixed(1)}%` : '--'}</span></span>
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
		gap: var(--space-2xs) var(--space-md);
		padding: var(--space-xs) 0;
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.item {
		display: flex;
		align-items: baseline;
		gap: var(--space-xs);
	}
	.lbl {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}
	.val {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.sep {
		width: 1px;
		height: 0.75rem;
		background: var(--rule-strong);
	}
	.yeast {
		color: var(--ink-secondary);
	}
	.recipe-name {
		color: var(--ink-muted);
	}
</style>
