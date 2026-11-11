<script lang="ts">
	import { onMount } from 'svelte';
	import type { RecipeResponse } from '$lib/api';
	import { fetchRecipes } from '$lib/api';

	interface Props {
		selectedRecipeId?: number;
		onSelect: (recipe: RecipeResponse | null) => void;
	}

	let { selectedRecipeId, onSelect }: Props = $props();

	let recipes = $state<RecipeResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');

	let filteredRecipes = $derived(
		recipes.filter(
			(r) =>
				!searchQuery ||
				r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				r.author?.toLowerCase().includes(searchQuery.toLowerCase())
		)
	);

	let selectedRecipe = $derived(
		selectedRecipeId ? recipes.find((r) => r.id === selectedRecipeId) : null
	);

	onMount(async () => {
		try {
			recipes = await fetchRecipes();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load recipes';
			console.error('Failed to load recipes:', e);
		} finally {
			loading = false;
		}
	});

	function handleSelect(recipe: RecipeResponse) {
		onSelect(recipe);
	}

	function handleClear() {
		onSelect(null);
	}
</script>

<div class="recipe-selector">
	<div class="selector-header">
		<label for="recipe-search" class="selector-label">Select Recipe (Optional)</label>
		{#if selectedRecipe}
			<button type="button" class="clear-btn" onclick={handleClear}>Clear Selection</button>
		{/if}
	</div>

	{#if loading}
		<div class="loading">
			<div class="spinner"></div>
			<p>Loading recipes...</p>
		</div>
	{:else if error}
		<div class="error-box">
			<p class="error-text">{error}</p>
		</div>
	{:else if recipes.length === 0}
		<div class="empty">
			<p class="empty-text">No recipes yet.</p>
			<a href="/recipes/import" class="import-link">Import your first recipe</a>
		</div>
	{:else}
		{#if selectedRecipe}
			<div class="selected-recipe">
				<div class="recipe-info">
					<p class="recipe-name">{selectedRecipe.name}</p>
					{#if selectedRecipe.og && selectedRecipe.fg}
						<p class="recipe-gravity">
							{selectedRecipe.og.toFixed(3)} → {selectedRecipe.fg.toFixed(3)}
						</p>
					{/if}
					{#if selectedRecipe.yeast_name}
						<p class="recipe-yeast">{selectedRecipe.yeast_name}</p>
					{/if}
				</div>
			</div>
		{:else}
			<input
				id="recipe-search"
				type="text"
				placeholder="Search recipes..."
				bind:value={searchQuery}
				class="search-input"
			/>

			<div class="recipe-list">
				{#each filteredRecipes as recipe (recipe.id)}
					<button type="button" class="recipe-item" onclick={() => handleSelect(recipe)}>
						<span class="recipe-item-name">{recipe.name}</span>
						{#if recipe.og}
							<span class="recipe-item-og">{recipe.og.toFixed(3)}</span>
						{/if}
					</button>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<style>
	.recipe-selector {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-3) 0;
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.selector-label {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
	}

	.clear-btn {
		min-height: 32px;
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		background: transparent;
		border: none;
		cursor: pointer;
		padding: var(--space-1) var(--space-2);
	}

	.clear-btn:hover {
		color: var(--accent);
	}

	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-6);
	}

	.spinner {
		width: 24px;
		height: 24px;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-6);
	}

	.empty-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: 0;
	}

	.error-box {
		padding: var(--space-3) 0;
		border-top: 1px solid var(--status-danger);
	}

	.error-text {
		font-size: var(--text-sm);
		color: var(--status-danger);
		margin: 0;
		text-align: center;
	}

	.import-link {
		font-size: var(--text-sm);
		color: var(--accent);
		text-decoration: none;
	}

	.import-link:hover {
		text-decoration: underline;
	}

	.selected-recipe {
		padding: 0;
	}

	.recipe-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.recipe-name {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.recipe-gravity,
	.recipe-yeast {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		font-family: var(--font-num);
		margin: 0;
	}

	.search-input {
		width: 100%;
		min-height: 44px;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-size: var(--text-sm);
	}

	.search-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.recipe-list {
		display: flex;
		flex-direction: column;
		max-height: 300px;
		overflow-y: auto;
	}

	.recipe-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		min-height: 44px;
		padding: var(--space-2) var(--space-1);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--rule-hairline);
		text-align: left;
		cursor: pointer;
	}

	.recipe-item:hover {
		background: var(--bg-surface);
	}

	.recipe-item-name {
		font-size: var(--text-sm);
		color: var(--ink-primary);
		flex: 1;
	}

	.recipe-item-og {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		font-family: var(--font-num);
	}
</style>
