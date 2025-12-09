<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { RecipeResponse } from '$lib/api';
	import { fetchRecipes } from '$lib/api';
	import RecipeCard from '$lib/components/RecipeCard.svelte';

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

	onMount(async () => {
		try {
			recipes = await fetchRecipes();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load recipes';
		} finally {
			loading = false;
		}
	});

	function handleRecipeClick(recipeId: number) {
		goto(`/recipes/${recipeId}`);
	}
</script>

<svelte:head>
	<title>Recipes | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<div class="header-left">
			<h1 class="page-title">Recipes</h1>
			{#if !loading && recipes.length > 0}
				<span class="recipe-count">{filteredRecipes.length} of {recipes.length}</span>
			{/if}
		</div>
		<div class="header-actions">
			<a href="/recipes/new" class="new-btn">
				<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				New Recipe
			</a>
			<a href="/recipes/import" class="import-btn">
				<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
				</svg>
				Import
			</a>
		</div>
	</div>

	{#if recipes.length > 0}
		<div class="search-bar">
			<input
				type="text"
				placeholder="Search recipes..."
				bind:value={searchQuery}
				class="search-input"
			/>
		</div>
	{/if}

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading recipes...</p>
		</div>
	{:else if error}
		<div class="error-state">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipes.length === 0}
		<div class="empty-state">
			<div class="empty-icon">📖</div>
			<h2 class="empty-title">No Recipes Yet</h2>
			<p class="empty-description">Import your first BeerXML recipe to get started</p>
			<a href="/recipes/import" class="empty-cta">Import Recipe</a>
		</div>
	{:else if filteredRecipes.length === 0}
		<div class="empty-state">
			<p class="empty-description">No recipes match "{searchQuery}"</p>
		</div>
	{:else}
		<div class="recipe-grid">
			{#each filteredRecipes as recipe (recipe.id)}
				<RecipeCard {recipe} onclick={() => handleRecipeClick(recipe.id)} />
			{/each}
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: var(--space-6);
	}

	.header-left {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
	}

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.recipe-count {
		font-size: 14px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.header-actions {
		display: flex;
		gap: var(--space-3);
	}

	.new-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-4);
		background: var(--recipe-accent);
		color: white;
		text-decoration: none;
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		transition: background var(--transition);
	}

	.new-btn:hover {
		background: var(--recipe-accent-hover);
	}

	.import-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-4);
		background: var(--recipe-accent);
		color: white;
		text-decoration: none;
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		transition: background var(--transition);
	}

	.import-btn:hover {
		background: var(--recipe-accent-hover);
	}

	.icon {
		width: 16px;
		height: 16px;
	}

	.search-bar {
		margin-bottom: var(--space-6);
	}

	.search-input {
		width: 100%;
		max-width: 400px;
		padding: var(--space-3) var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
		font-family: var(--font-sans);
	}

	.search-input:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.recipe-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
		gap: var(--space-4);
	}

	.loading-state,
	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-12) var(--space-6);
		text-align: center;
	}

	.spinner {
		width: 32px;
		height: 32px;
		border: 3px solid var(--gray-700);
		border-top-color: var(--recipe-accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.empty-icon {
		font-size: 48px;
		margin-bottom: var(--space-4);
	}

	.empty-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 var(--space-2) 0;
	}

	.empty-description {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0 0 var(--space-6) 0;
	}

	.empty-cta {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-5);
		background: var(--recipe-accent);
		color: white;
		text-decoration: none;
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		transition: background var(--transition);
	}

	.empty-cta:hover {
		background: var(--recipe-accent-hover);
	}

	.error-state {
		padding: var(--space-6);
		text-align: center;
	}

	.error-message {
		color: var(--negative);
		font-size: 14px;
	}
</style>
