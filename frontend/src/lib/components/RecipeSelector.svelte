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
		padding: var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.selector-label {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.clear-btn {
		font-size: 12px;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		cursor: pointer;
		padding: var(--space-1) var(--space-2);
		transition: color var(--transition);
	}

	.clear-btn:hover {
		color: var(--recipe-accent);
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
		border: 2px solid var(--gray-700);
		border-top-color: var(--recipe-accent);
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
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.error-box {
		padding: var(--space-4);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid var(--negative);
		border-radius: 6px;
	}

	.error-text {
		font-size: 14px;
		color: var(--negative);
		margin: 0;
		text-align: center;
	}

	.import-link {
		font-size: 13px;
		color: var(--recipe-accent);
		text-decoration: none;
	}

	.import-link:hover {
		text-decoration: underline;
	}

	.selected-recipe {
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--recipe-accent-border);
		border-radius: 6px;
	}

	.recipe-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.recipe-name {
		font-family: var(--font-recipe-name);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.recipe-gravity,
	.recipe-yeast {
		font-size: 13px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
		margin: 0;
	}

	.search-input {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
	}

	.search-input:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.recipe-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		max-height: 300px;
		overflow-y: auto;
	}

	.recipe-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 4px;
		text-align: left;
		cursor: pointer;
		transition: all var(--transition);
	}

	.recipe-item:hover {
		border-color: var(--recipe-accent-border);
		background: var(--bg-hover);
	}

	.recipe-item-name {
		font-size: 14px;
		color: var(--text-primary);
		flex: 1;
	}

	.recipe-item-og {
		font-size: 12px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}
</style>
