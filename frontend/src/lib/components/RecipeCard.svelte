<script lang="ts">
	import type { RecipeResponse } from '$lib/api';

	interface Props {
		recipe: RecipeResponse;
		onclick?: () => void;
	}

	let { recipe, onclick }: Props = $props();

	// Calculate SRM color gradient
	function getSrmColor(srm?: number): string {
		if (!srm) return 'var(--gray-600)';
		if (srm < 6) return '#f6e5a8';
		if (srm < 12) return '#e5a840';
		if (srm < 20) return '#d87a3a';
		if (srm < 30) return '#8b4513';
		return '#1a0f0a';
	}

	let srmColor = $derived(getSrmColor(recipe.srm_target));
</script>

<button type="button" class="recipe-card" {onclick} aria-label="View {recipe.name} details">
	<div class="recipe-header">
		<h3 class="recipe-name">{recipe.name}</h3>
		<div class="recipe-meta">
			{#if recipe.type}
				<span class="recipe-type">{recipe.type}</span>
			{/if}
			{#if recipe.abv_target}
				<span class="recipe-abv">{recipe.abv_target.toFixed(1)}% ABV</span>
			{/if}
		</div>
	</div>

	{#if recipe.srm_target}
		<div class="srm-bar" style="background: {srmColor}"></div>
	{/if}

	<div class="recipe-stats">
		{#if recipe.og_target && recipe.fg_target}
			<div class="stat">
				<span class="stat-label">Gravity</span>
				<span class="stat-value">{recipe.og_target.toFixed(3)} → {recipe.fg_target.toFixed(3)}</span>
			</div>
		{/if}

		{#if recipe.yeast_name}
			<div class="stat">
				<span class="stat-label">Yeast</span>
				<span class="stat-value">{recipe.yeast_name}</span>
			</div>
		{/if}
	</div>
</button>

<style>
	.recipe-card {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		text-align: left;
		width: 100%;
		cursor: pointer;
		transition: all var(--transition);
	}

	.recipe-card:hover {
		transform: translateY(-2px);
		border-color: var(--recipe-accent-border);
		box-shadow: 0 4px 12px var(--recipe-accent-muted);
	}

	.recipe-header {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.recipe-name {
		font-family: var(--font-recipe-name);
		font-size: 18px;
		font-weight: 600;
		letter-spacing: -0.02em;
		color: var(--text-primary);
		margin: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.recipe-meta {
		display: flex;
		gap: var(--space-2);
		font-size: 12px;
		color: var(--text-secondary);
	}

	.recipe-type,
	.recipe-abv {
		font-family: var(--font-mono);
	}

	.srm-bar {
		height: 6px;
		border-radius: 3px;
		margin: var(--space-1) 0;
	}

	.recipe-stats {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.stat {
		display: flex;
		justify-content: space-between;
		font-size: 13px;
	}

	.stat-label {
		color: var(--text-secondary);
	}

	.stat-value {
		font-family: var(--font-measurement);
		color: var(--text-primary);
	}
</style>
