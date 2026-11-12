<script lang="ts">
	import { recipeUrl } from '$lib/urls';
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import type { RecipeResponse } from '$lib/api';
	import { fetchRecipes } from '$lib/api';
	import { srmToHex } from '$lib/brewing';

	let recipes = $state<RecipeResponse[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');

	let filteredRecipes = $derived(
		recipes.filter(
			(r) =>
				!searchQuery ||
				r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				r.author?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				r.style?.name?.toLowerCase().includes(searchQuery.toLowerCase())
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

	function handleRecipeClick(e: MouseEvent, recipe: { id: number; name?: string | null }) {
		// Let modified clicks (new tab/window) fall through to the anchor.
		if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
		e.preventDefault();
		goto(recipeUrl(recipe));
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
				<span class="recipe-count">{filteredRecipes.length}&thinsp;/&thinsp;{recipes.length}</span>
			{/if}
		</div>
		<div class="header-actions">
			<a href="/recipes/new" class="btn-primary">
				<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				New Recipe
			</a>
			<a href="/recipes/import" class="btn-secondary">
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
				type="search"
				placeholder="Search recipes..."
				aria-label="Search recipes"
				bind:value={searchQuery}
				class="search-input"
			/>
		</div>
	{/if}

	{#if loading}
		<div class="state-block">
			<div class="spinner"></div>
			<p>Loading recipes...</p>
		</div>
	{:else if error}
		<div class="state-block">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipes.length === 0}
		<div class="state-block">
			<h2 class="empty-title">No recipes yet</h2>
			<p class="empty-description">Import your first BeerXML recipe to get started</p>
			<a href="/recipes/import" class="btn-primary">Import Recipe</a>
		</div>
	{:else if filteredRecipes.length === 0}
		<div class="state-block">
			<p class="empty-description">No recipes match "{searchQuery}"</p>
		</div>
	{:else}
		<div class="recipe-table" role="table" aria-label="Recipes">
			<div class="row head" role="row">
				<span class="c-name" role="columnheader">Recipe</span>
				<span class="c-type" role="columnheader">Type</span>
				<span class="c-gravity num" role="columnheader">OG → FG</span>
				<span class="c-abv num" role="columnheader">ABV</span>
				<span class="c-ibu num" role="columnheader">IBU</span>
				<span class="c-srm num" role="columnheader">SRM</span>
			</div>
			{#each filteredRecipes as recipe (recipe.id)}
				<a
					class="row item"
					role="row"
					href={recipeUrl(recipe)}
					onclick={(e) => handleRecipeClick(e, recipe)}
					aria-label="View {recipe.name} details"
				>
					<span class="c-name" role="cell">
						<span class="recipe-name">{recipe.name}</span>
						{#if recipe.style?.name || recipe.author}
							<span class="recipe-sub">{recipe.style?.name ?? `by ${recipe.author}`}</span>
						{/if}
					</span>
					<span class="c-type" role="cell">{recipe.type ?? ''}</span>
					<span class="c-gravity num" role="cell" data-label="OG → FG">
						{#if recipe.og && recipe.fg}{recipe.og.toFixed(3)}&nbsp;→&nbsp;{recipe.fg.toFixed(3)}{:else}<span class="dash">--</span>{/if}
					</span>
					<span class="c-abv num" role="cell" data-label="ABV">
						{#if recipe.abv}{recipe.abv.toFixed(1)}%{:else}<span class="dash">--</span>{/if}
					</span>
					<span class="c-ibu num" role="cell" data-label="IBU">
						{#if recipe.ibu}{recipe.ibu.toFixed(0)}{:else}<span class="dash">--</span>{/if}
					</span>
					<span class="c-srm num" role="cell" data-label="SRM">
						{#if recipe.color_srm}<!-- Beer colour is data (SRM), not theme --><span class="swatch" style="background: {srmToHex(recipe.color_srm)}"></span>{recipe.color_srm.toFixed(0)}{:else}<span class="dash">--</span>{/if}
					</span>
				</a>
			{/each}
		</div>
	{/if}
</div>

<style>
	.page-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: var(--space-lg);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-md);
		flex-wrap: wrap;
		margin-bottom: var(--space-lg);
	}

	.header-left {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
	}

	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 600;
		margin: 0;
		color: var(--ink-primary);
	}

	.recipe-count {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-muted);
	}

	.header-actions {
		display: flex;
		gap: var(--space-xs);
	}

	.btn-primary,
	.btn-secondary {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-xs) var(--space-md);
		min-height: 36px;
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		white-space: nowrap;
		text-decoration: none;
		transition: background var(--transition), border-color var(--transition), color var(--transition);
	}

	.btn-primary {
		background: var(--accent);
		border: 1px solid var(--accent);
		color: var(--accent-ink);
	}

	.btn-primary:hover {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.btn-secondary {
		background: transparent;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}

	.btn-secondary:hover {
		border-color: var(--ink-secondary);
		color: var(--ink-primary);
	}

	.icon {
		width: 16px;
		height: 16px;
	}

	.search-bar {
		margin-bottom: var(--space-md);
	}

	.search-input {
		width: 100%;
		max-width: 400px;
		padding: var(--space-xs) var(--space-sm);
		min-height: 36px;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-size: var(--text-sm);
		font-family: var(--font-body);
	}

	.search-input::placeholder {
		color: var(--ink-muted);
	}

	.search-input:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
	}

	/* Instrument table: hairline rows, equal structure */
	.recipe-table {
		border: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
	}

	.row {
		display: grid;
		grid-template-columns: minmax(0, 1fr) 150px 140px 72px 56px 64px;
		align-items: center;
		column-gap: var(--space-md);
		padding: var(--space-sm) var(--space-md);
	}

	.row + .row {
		border-top: 1px solid var(--rule-hairline);
	}

	.row.head {
		padding-block: var(--space-xs);
		background: var(--bg-elevated);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}

	.row.item {
		color: var(--ink-primary);
		text-decoration: none;
		transition: background var(--transition);
	}

	.row.item:hover {
		background: var(--bg-subtle);
	}

	.row.item:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	/* Calibrated SRM swatch: beer colour is data, outlined so dark beers stay visible */
	.swatch {
		display: inline-block;
		width: 10px;
		height: 10px;
		margin-right: var(--space-xs);
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
		vertical-align: -1px;
	}

	.c-name {
		display: flex;
		flex-direction: column;
		min-width: 0;
		gap: 2px;
	}

	.recipe-name {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.recipe-sub {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.c-type {
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.06em;
		color: var(--ink-secondary);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}

	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		text-align: right;
		white-space: nowrap;
	}

	.dash {
		color: var(--ink-muted);
	}


	.state-block {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-sm);
		padding: var(--space-2xl) var(--space-lg);
		text-align: center;
		border: 1px solid var(--rule-hairline);
		color: var(--ink-secondary);
	}

	.state-block p {
		margin: 0;
	}

	.spinner {
		width: 28px;
		height: 28px;
		border: 2px solid var(--rule-strong);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation-duration: 2.4s;
		}
	}

	.empty-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.empty-description {
		font-size: var(--text-sm);
	}

	.error-message {
		color: var(--status-danger);
		font-size: var(--text-sm);
	}

	/* Tablet: drop the type column */
	@media (max-width: 1040px) {
		.row {
			grid-template-columns: minmax(0, 1fr) 140px 64px 48px 64px;
			column-gap: var(--space-sm);
		}

		.c-type {
			display: none;
		}
	}

	/* Phone: two-line rows, labelled stats */
	@media (max-width: 760px) {
		.page-container {
			padding: var(--space-md);
		}

		.row.head {
			display: none;
		}

		.btn-primary,
		.btn-secondary,
		.search-input {
			min-height: 44px;
		}

		.row {
			grid-template-columns: minmax(0, 1fr) auto auto auto;
			grid-template-areas:
				'name name name name'
				'gravity abv ibu srm';
			row-gap: var(--space-xs);
			column-gap: var(--space-md);
		}

		.c-name {
			grid-area: name;
		}

		.c-gravity {
			grid-area: gravity;
			text-align: left;
		}

		.c-abv {
			grid-area: abv;
		}

		.c-ibu {
			grid-area: ibu;
		}

		.c-srm {
			grid-area: srm;
		}

		.c-srm .swatch {
			margin-right: var(--space-2xs);
		}

		.num::before {
			content: attr(data-label);
			display: block;
			font-family: var(--font-body);
			font-size: 0.625rem;
			font-weight: 600;
			letter-spacing: 0.08em;
			text-transform: uppercase;
			color: var(--ink-muted);
		}
	}
</style>
