# Recipe UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build frontend UI for BeerXML recipe import and management using existing backend API.

**Architecture:** Three main routes (`/recipes`, `/recipes/import`, `/recipes/[id]`) with reusable components. Laboratory notebook aesthetic with amber accents. Integration with existing batch creation workflow.

**Tech Stack:** SvelteKit, TypeScript, Svelte 5 runes, CSS variables, Crimson Pro + JetBrains Mono fonts

**Reference Design:** `docs/plans/2025-12-02-recipe-ui-design.md`

---

## Task 1: Add Font Imports and Recipe Color Tokens

**Files:**
- Modify: `frontend/src/app.css` (add fonts and recipe colors)

**Step 1: Add Google Fonts import for Crimson Pro and JetBrains Mono**

In `frontend/src/app.css`, after the existing Geist font import (line 6), add:

```css
@import url('https://fonts.googleapis.com/css2?family=Crimson+Pro:wght@400;600&family=JetBrains+Mono:wght@400;500&display=swap');
```

**Step 2: Add recipe font CSS variables**

In `frontend/src/app.css`, after the existing font stack variables (around line 11), add:

```css
  --font-recipe-name: 'Crimson Pro', Georgia, serif;
  --font-measurement: 'JetBrains Mono', var(--font-mono);
```

**Step 3: Add recipe color tokens**

In `frontend/src/app.css`, after the existing accent colors (around line 50), add:

```css
  /* Recipe-specific accent (warm amber) */
  --recipe-accent: #f59e0b;
  --recipe-accent-hover: #d97706;
  --recipe-accent-muted: rgba(245, 158, 11, 0.15);
  --recipe-accent-border: rgba(245, 158, 11, 0.3);
```

**Step 4: Test font and color tokens load correctly**

Run: `cd frontend && npm run dev`

Expected: Dev server starts without errors, fonts load in browser

**Step 5: Commit**

```bash
git add frontend/src/app.css
git commit -m "feat: add recipe UI fonts and color tokens

- Import Crimson Pro (serif) for recipe names
- Import JetBrains Mono for measurements
- Add amber accent color variables for recipe UI

Part of #32"
```

---

## Task 2: Add Recipe API Functions

**Files:**
- Modify: `frontend/src/lib/api.ts` (add recipe API calls)

**Step 1: Add recipe API functions after existing batch APIs**

In `frontend/src/lib/api.ts`, after the batch functions (around line 150), add:

```typescript
// ============================================================================
// Recipe Types & API
// ============================================================================

export async function fetchRecipes(limit = 50, offset = 0): Promise<RecipeResponse[]> {
	const response = await fetch(`${BASE_URL}/recipes?limit=${limit}&offset=${offset}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch recipes: ${response.statusText}`);
	}
	return response.json();
}

export async function fetchRecipe(id: number): Promise<RecipeResponse> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`);
	if (!response.ok) {
		throw new Error(`Failed to fetch recipe: ${response.statusText}`);
	}
	return response.json();
}

export async function importBeerXML(file: File): Promise<RecipeResponse[]> {
	const formData = new FormData();
	formData.append('file', file);

	const response = await fetch(`${BASE_URL}/recipes/import`, {
		method: 'POST',
		body: formData
	});

	if (!response.ok) {
		const error = await response.json().catch(() => ({ detail: response.statusText }));
		throw new Error(error.detail || 'Failed to import recipe');
	}

	return response.json();
}

export async function deleteRecipe(id: number): Promise<void> {
	const response = await fetch(`${BASE_URL}/recipes/${id}`, {
		method: 'DELETE'
	});

	if (!response.ok) {
		throw new Error(`Failed to delete recipe: ${response.statusText}`);
	}
}
```

**Step 2: Verify TypeScript types already exist**

Run: `grep -A 15 "export interface RecipeResponse" frontend/src/lib/api.ts`

Expected: Should show RecipeResponse interface already defined (from lines 72-92)

**Step 3: Test API functions compile**

Run: `cd frontend && npm run check`

Expected: No TypeScript errors

**Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: add recipe API functions

- fetchRecipes: list all recipes
- fetchRecipe: get single recipe by ID
- importBeerXML: upload BeerXML file
- deleteRecipe: remove recipe

Part of #32"
```

---

## Task 3: Create RecipeCard Component

**Files:**
- Create: `frontend/src/lib/components/RecipeCard.svelte`

**Step 1: Create RecipeCard component file**

Create file: `frontend/src/lib/components/RecipeCard.svelte`

```svelte
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

<button type="button" class="recipe-card" {onclick}>
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
```

**Step 2: Test component renders**

Create test page at `frontend/src/routes/test-recipe-card/+page.svelte`:

```svelte
<script lang="ts">
	import RecipeCard from '$lib/components/RecipeCard.svelte';

	const testRecipe = {
		id: 1,
		name: 'Sample Blonde Ale',
		type: 'All Grain',
		og_target: 1.044,
		fg_target: 1.008,
		abv_target: 4.7,
		srm_target: 8.5,
		yeast_name: 'US-05',
		created_at: '2025-12-02T00:00:00Z'
	};
</script>

<div style="padding: 2rem; max-width: 300px;">
	<RecipeCard recipe={testRecipe} onclick={() => alert('Clicked!')} />
</div>
```

Run: Navigate to http://localhost:5173/test-recipe-card in browser

Expected: Recipe card displays with amber hover effect

**Step 3: Remove test page**

Run: `rm frontend/src/routes/test-recipe-card/+page.svelte`

**Step 4: Commit**

```bash
git add frontend/src/lib/components/RecipeCard.svelte
git commit -m "feat: add RecipeCard component

- Specimen box aesthetic with amber accent on hover
- Shows recipe name (Crimson Pro serif)
- SRM color bar visualization
- Gravity range and yeast in monospace font
- Clickable for navigation

Part of #32"
```

---

## Task 4: Create Recipe List Page

**Files:**
- Create: `frontend/src/routes/recipes/+page.svelte`

**Step 1: Create recipes directory**

Run: `mkdir -p frontend/src/routes/recipes`

**Step 2: Create recipe list page**

Create file: `frontend/src/routes/recipes/+page.svelte`

```svelte
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
		<a href="/recipes/import" class="import-btn">
			<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
			</svg>
			Import Recipe
		</a>
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
```

**Step 3: Test recipe list page**

Run: `cd frontend && npm run dev`

Navigate to: http://localhost:5173/recipes

Expected: Shows empty state with "Import Recipe" button (no recipes yet)

**Step 4: Commit**

```bash
git add frontend/src/routes/recipes/+page.svelte
git commit -m "feat: add recipe list page

- Grid layout with RecipeCard components
- Search bar filters by name/author
- Empty state with import CTA
- Loading and error states
- Amber accent styling

Part of #32"
```

---

## Task 5: Create Recipe Import Page

**Files:**
- Create: `frontend/src/routes/recipes/import/+page.svelte`

**Step 1: Create import directory**

Run: `mkdir -p frontend/src/routes/recipes/import`

**Step 2: Create recipe import page**

Create file: `frontend/src/routes/recipes/import/+page.svelte`

```svelte
<script lang="ts">
	import { goto } from '$app/navigation';
	import { importBeerXML } from '$lib/api';

	let uploading = $state(false);
	let error = $state<string | null>(null);
	let dragActive = $state(false);

	async function handleFileUpload(file: File) {
		error = null;

		// Validate file
		if (!file.name.endsWith('.xml')) {
			error = 'Please upload a .xml BeerXML file';
			return;
		}

		if (file.size > 1_000_000) {
			error = 'File must be smaller than 1MB';
			return;
		}

		uploading = true;

		try {
			const recipes = await importBeerXML(file);
			// Redirect to first imported recipe or back to list
			if (recipes.length === 1) {
				goto(`/recipes/${recipes[0].id}`);
			} else {
				goto('/recipes');
			}
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to import recipe';
		} finally {
			uploading = false;
		}
	}

	function handleDrop(e: DragEvent) {
		e.preventDefault();
		dragActive = false;

		const file = e.dataTransfer?.files[0];
		if (file) {
			handleFileUpload(file);
		}
	}

	function handleDragOver(e: DragEvent) {
		e.preventDefault();
		dragActive = true;
	}

	function handleDragLeave() {
		dragActive = false;
	}

	function handleFileInput(e: Event) {
		const input = e.target as HTMLInputElement;
		const file = input.files?.[0];
		if (file) {
			handleFileUpload(file);
		}
	}
</script>

<svelte:head>
	<title>Import Recipe | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipes
		</a>
	</div>

	<div class="import-container">
		<h1 class="page-title">Import Recipe</h1>
		<p class="page-description">
			Upload BeerXML files from Brewfather, BeerSmith, Brewer's Friend, or any brewing software
		</p>

		<div
			class="drop-zone"
			class:active={dragActive}
			class:uploading
			ondrop={handleDrop}
			ondragover={handleDragOver}
			ondragleave={handleDragLeave}
			role="button"
			tabindex="0"
		>
			{#if uploading}
				<div class="spinner"></div>
				<p class="drop-text">Importing recipe...</p>
			{:else}
				<div class="upload-icon">📄</div>
				<p class="drop-text">Drop BeerXML file here</p>
				<p class="drop-subtext">or click to browse</p>
				<input
					type="file"
					accept=".xml"
					onchange={handleFileInput}
					class="file-input"
					disabled={uploading}
				/>
			{/if}
		</div>

		<div class="file-info">
			<p class="info-text">Supported: .xml files (max 1MB)</p>
		</div>

		{#if error}
			<div class="error-box">
				<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path
						stroke-linecap="round"
						stroke-linejoin="round"
						d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
					/>
				</svg>
				<p class="error-text">{error}</p>
			</div>
		{/if}
	</div>
</div>

<style>
	.page-container {
		max-width: 600px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.back-link {
		margin-bottom: var(--space-6);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	.import-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.page-description {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.drop-zone {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-3);
		padding: var(--space-12) var(--space-6);
		background: var(--bg-surface);
		border: 2px dashed var(--border-default);
		border-radius: 8px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.drop-zone:hover:not(.uploading) {
		border-color: var(--recipe-accent-border);
		background: var(--bg-elevated);
	}

	.drop-zone.active {
		border-color: var(--recipe-accent);
		background: var(--recipe-accent-muted);
	}

	.drop-zone.uploading {
		cursor: wait;
		opacity: 0.7;
	}

	.upload-icon {
		font-size: 48px;
	}

	.drop-text {
		font-size: 16px;
		font-weight: 500;
		color: var(--text-primary);
		margin: 0;
	}

	.drop-subtext {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.file-input {
		position: absolute;
		inset: 0;
		opacity: 0;
		cursor: pointer;
	}

	.file-input:disabled {
		cursor: wait;
	}

	.file-info {
		display: flex;
		justify-content: center;
	}

	.info-text {
		font-size: 12px;
		color: var(--text-muted);
		margin: 0;
		font-family: var(--font-mono);
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

	.error-box {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-4);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid var(--negative);
		border-radius: 6px;
	}

	.error-icon {
		width: 20px;
		height: 20px;
		color: var(--negative);
		flex-shrink: 0;
	}

	.error-text {
		font-size: 14px;
		color: var(--negative);
		margin: 0;
	}
</style>
```

**Step 3: Test import page**

Run: Navigate to http://localhost:5173/recipes/import

Expected: Shows drop zone with drag-and-drop and file input

**Step 4: Test error handling**

Try uploading a non-XML file or file >1MB

Expected: Shows error message

**Step 5: Commit**

```bash
git add frontend/src/routes/recipes/import/+page.svelte
git commit -m "feat: add recipe import page

- Drag-and-drop BeerXML file upload
- File input fallback
- Validation for file type and size (1MB max)
- Loading and error states
- Redirects to recipe detail or list after import

Part of #32"
```

---

## Task 6: Create Recipe Detail Page

**Files:**
- Create: `frontend/src/routes/recipes/[id]/+page.svelte`

**Step 1: Create recipe detail directory**

Run: `mkdir -p frontend/src/routes/recipes/[id]`

**Step 2: Create recipe detail page**

Create file: `frontend/src/routes/recipes/[id]/+page.svelte`

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse } from '$lib/api';
	import { fetchRecipe, deleteRecipe } from '$lib/api';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	let recipeId = $derived(parseInt($page.params.id, 10));

	onMount(async () => {
		try {
			recipe = await fetchRecipe(recipeId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load recipe';
		} finally {
			loading = false;
		}
	});

	async function handleDelete() {
		if (!recipe) return;

		deleting = true;
		try {
			await deleteRecipe(recipe.id);
			goto('/recipes');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete recipe';
			deleting = false;
			showDeleteConfirm = false;
		}
	}

	function handleBrewThis() {
		if (!recipe) return;
		goto(`/batches/new?recipe_id=${recipe.id}`);
	}
</script>

<svelte:head>
	<title>{recipe?.name || 'Recipe'} | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipes
		</a>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading recipe...</p>
		</div>
	{:else if error}
		<div class="error-state">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipe}
		<div class="recipe-container">
			<div class="recipe-header">
				<div class="header-left">
					<h1 class="recipe-title">{recipe.name}</h1>
					{#if recipe.author}
						<p class="recipe-author">by {recipe.author}</p>
					{/if}
					{#if recipe.type}
						<p class="recipe-type">{recipe.type}</p>
					{/if}
				</div>
				<button type="button" class="delete-btn" onclick={() => (showDeleteConfirm = true)}>
					<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
						/>
					</svg>
					Delete
				</button>
			</div>

			<div class="section">
				<h2 class="section-title">Fermentation Parameters</h2>
				<div class="param-grid">
					{#if recipe.og_target}
						<div class="param">
							<span class="param-label">Original Gravity</span>
							<span class="param-value">{recipe.og_target.toFixed(3)}</span>
						</div>
					{/if}
					{#if recipe.fg_target}
						<div class="param">
							<span class="param-label">Final Gravity</span>
							<span class="param-value">{recipe.fg_target.toFixed(3)}</span>
						</div>
					{/if}
					{#if recipe.abv_target}
						<div class="param">
							<span class="param-label">ABV</span>
							<span class="param-value">{recipe.abv_target.toFixed(1)}%</span>
						</div>
					{/if}
					{#if recipe.yeast_attenuation}
						<div class="param">
							<span class="param-label">Attenuation</span>
							<span class="param-value">{recipe.yeast_attenuation.toFixed(0)}%</span>
						</div>
					{/if}
				</div>
			</div>

			{#if recipe.yeast_name || recipe.yeast_temp_min || recipe.yeast_temp_max}
				<div class="section">
					<h2 class="section-title">Yeast</h2>
					<div class="yeast-info">
						{#if recipe.yeast_name}
							<p class="yeast-name">{recipe.yeast_name}</p>
						{/if}
						{#if recipe.yeast_lab}
							<p class="yeast-lab">{recipe.yeast_lab}</p>
						{/if}
						{#if recipe.yeast_temp_min !== undefined && recipe.yeast_temp_max !== undefined}
							<p class="yeast-temp">
								Temperature: {recipe.yeast_temp_min.toFixed(0)}-{recipe.yeast_temp_max.toFixed(0)}°C
							</p>
						{/if}
					</div>
				</div>
			{/if}

			<div class="section">
				<h2 class="section-title">Batch Details</h2>
				<div class="details-grid">
					{#if recipe.batch_size}
						<div class="detail">
							<span class="detail-label">Batch Size</span>
							<span class="detail-value">{recipe.batch_size.toFixed(1)} L</span>
						</div>
					{/if}
					{#if recipe.ibu_target}
						<div class="detail">
							<span class="detail-label">IBU</span>
							<span class="detail-value">{recipe.ibu_target.toFixed(0)}</span>
						</div>
					{/if}
					{#if recipe.srm_target}
						<div class="detail">
							<span class="detail-label">SRM</span>
							<span class="detail-value">{recipe.srm_target.toFixed(1)}</span>
						</div>
					{/if}
				</div>
			</div>

			{#if recipe.notes}
				<div class="section">
					<h2 class="section-title">Notes</h2>
					<p class="notes">{recipe.notes}</p>
				</div>
			{/if}

			<div class="section">
				<p class="created-date">Created {new Date(recipe.created_at).toLocaleDateString()}</p>
			</div>

			<div class="actions">
				<button type="button" class="brew-btn" onclick={handleBrewThis}>
					<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path
							stroke-linecap="round"
							stroke-linejoin="round"
							d="M12 6v6m0 0v6m0-6h6m-6 0H6"
						/>
					</svg>
					Brew This Recipe
				</button>
			</div>
		</div>
	{/if}
</div>

{#if showDeleteConfirm}
	<div class="modal-overlay" onclick={() => (showDeleteConfirm = false)}>
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Delete Recipe?</h2>
			<p class="modal-text">
				Are you sure you want to delete "{recipe?.name}"? This cannot be undone.
			</p>
			<div class="modal-actions">
				<button
					type="button"
					class="modal-btn cancel"
					onclick={() => (showDeleteConfirm = false)}
					disabled={deleting}
				>
					Cancel
				</button>
				<button type="button" class="modal-btn delete" onclick={handleDelete} disabled={deleting}>
					{deleting ? 'Deleting...' : 'Delete Recipe'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container {
		max-width: 800px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.back-link {
		margin-bottom: var(--space-6);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--text-primary);
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	.loading-state,
	.error-state {
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

	.error-message {
		color: var(--negative);
		font-size: 14px;
	}

	.recipe-container {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.recipe-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-4);
		padding-bottom: var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
	}

	.header-left {
		flex: 1;
	}

	.recipe-title {
		font-family: var(--font-recipe-name);
		font-size: 32px;
		font-weight: 600;
		letter-spacing: -0.02em;
		color: var(--text-primary);
		margin: 0 0 var(--space-2) 0;
	}

	.recipe-author {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0 0 var(--space-1) 0;
	}

	.recipe-type {
		font-size: 13px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		margin: 0;
	}

	.delete-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: transparent;
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-secondary);
		font-size: 14px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.delete-btn:hover {
		border-color: var(--negative);
		color: var(--negative);
	}

	.icon {
		width: 16px;
		height: 16px;
	}

	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.section-title {
		font-size: 16px;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.param-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.param {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.param-label {
		font-size: 12px;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.param-value {
		font-family: var(--font-measurement);
		font-size: 20px;
		color: var(--text-primary);
	}

	.yeast-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.yeast-name {
		font-size: 16px;
		font-weight: 500;
		color: var(--text-primary);
		margin: 0;
	}

	.yeast-lab {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.yeast-temp {
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-secondary);
		margin: 0;
	}

	.details-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
		gap: var(--space-4);
	}

	.detail {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.detail-label {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.detail-value {
		font-family: var(--font-measurement);
		font-size: 16px;
		color: var(--text-primary);
	}

	.notes {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.6;
		margin: 0;
	}

	.created-date {
		font-size: 12px;
		color: var(--text-muted);
		font-family: var(--font-mono);
		margin: 0;
	}

	.actions {
		display: flex;
		justify-content: center;
		padding-top: var(--space-6);
		border-top: 1px solid var(--border-subtle);
	}

	.brew-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3) var(--space-6);
		background: var(--recipe-accent);
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 16px;
		font-weight: 600;
		cursor: pointer;
		transition: background var(--transition);
	}

	.brew-btn:hover {
		background: var(--recipe-accent-hover);
	}

	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 8px;
		padding: var(--space-6);
		max-width: 400px;
		width: 90%;
	}

	.modal-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 var(--space-3) 0;
	}

	.modal-text {
		font-size: 14px;
		color: var(--text-secondary);
		line-height: 1.5;
		margin: 0 0 var(--space-6) 0;
	}

	.modal-actions {
		display: flex;
		gap: var(--space-3);
		justify-content: flex-end;
	}

	.modal-btn {
		padding: var(--space-2) var(--space-4);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
	}

	.modal-btn.cancel {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.modal-btn.cancel:hover {
		background: var(--bg-hover);
	}

	.modal-btn.delete {
		background: var(--negative);
		border: none;
		color: white;
	}

	.modal-btn.delete:hover {
		background: #dc2626;
	}

	.modal-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
```

**Step 3: Test recipe detail page**

Navigate to: http://localhost:5173/recipes/1 (after importing a recipe)

Expected: Shows recipe details with laboratory notebook aesthetic

**Step 4: Test delete confirmation**

Click "Delete" button

Expected: Shows modal with confirmation, can cancel or delete

**Step 5: Commit**

```bash
git add frontend/src/routes/recipes/[id]/+page.svelte
git commit -m "feat: add recipe detail page

- Laboratory notebook layout with amber accents
- Fermentation parameters section (OG/FG/ABV/attenuation)
- Yeast information with temp ranges
- Batch details (size, IBU, SRM)
- Delete confirmation modal
- Brew This Recipe button → batch creation

Part of #32"
```

---

## Task 7: Add Recipes to Navigation

**Files:**
- Modify: `frontend/src/routes/+layout.svelte`

**Step 1: Add Recipes nav item**

In `frontend/src/routes/+layout.svelte`, find the navigation items array (around line 15-25) and add:

```typescript
const navItems = [
	{ href: '/', label: 'Dashboard', icon: 'dashboard' },
	{ href: '/batches', label: 'Batches', icon: 'batches' },
	{ href: '/recipes', label: 'Recipes', icon: 'recipes' },  // ADD THIS LINE
	{ href: '/calibration', label: 'Calibration', icon: 'calibration' },
	{ href: '/logging', label: 'Logging', icon: 'logging' },
	{ href: '/system', label: 'System', icon: 'system' }
];
```

**Step 2: Add recipe icon SVG**

Find the icon rendering section (around line 80-120) and add the recipe icon case:

```svelte
{#if item.icon === 'recipes'}
	<svg class="nav-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
		<path stroke-linecap="round" stroke-linejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
	</svg>
{:else if ...}
```

**Step 3: Test navigation**

Run: `cd frontend && npm run dev`

Navigate through: Dashboard → Batches → **Recipes** → Calibration

Expected: Recipes link appears in nav, highlights when active

**Step 4: Commit**

```bash
git add frontend/src/routes/+layout.svelte
git commit -m "feat: add Recipes to navigation

- Added Recipes nav item between Batches and Calibration
- Book icon for recipe library
- Active state highlighting

Part of #32"
```

---

## Task 8: Integrate Recipe Selector into Batch Form

**Files:**
- Create: `frontend/src/lib/components/RecipeSelector.svelte`
- Modify: `frontend/src/lib/components/BatchForm.svelte`

**Step 1: Create RecipeSelector component**

Create file: `frontend/src/lib/components/RecipeSelector.svelte`

```svelte
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
					{#if selectedRecipe.og_target && selectedRecipe.fg_target}
						<p class="recipe-gravity">
							{selectedRecipe.og_target.toFixed(3)} → {selectedRecipe.fg_target.toFixed(3)}
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
						{#if recipe.og_target}
							<span class="recipe-item-og">{recipe.og_target.toFixed(3)}</span>
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
```

**Step 2: Integrate RecipeSelector into BatchForm**

In `frontend/src/lib/components/BatchForm.svelte`, add recipe selector at the top of the form (after the title, around line 40):

First, add imports:
```typescript
import RecipeSelector from './RecipeSelector.svelte';
import type { RecipeResponse } from '$lib/api';
```

Then add state for selected recipe:
```typescript
let selectedRecipe = $state<RecipeResponse | null>(null);
```

Add handler function:
```typescript
function handleRecipeSelect(recipe: RecipeResponse | null) {
	selectedRecipe = recipe;
	if (recipe) {
		// Auto-fill form from recipe
		formData.name = recipe.name;
		if (recipe.og_target) {
			formData.measured_og = recipe.og_target;
		}
		// Display yeast info as reference (read-only)
	}
}
```

Add RecipeSelector before the name input:
```svelte
<RecipeSelector
	selectedRecipeId={selectedRecipe?.id}
	onSelect={handleRecipeSelect}
/>

{#if selectedRecipe}
	<div class="recipe-reference">
		<p class="reference-label">From Recipe:</p>
		{#if selectedRecipe.yeast_name}
			<p class="reference-text">
				Yeast: {selectedRecipe.yeast_name}
				{#if selectedRecipe.yeast_temp_min && selectedRecipe.yeast_temp_max}
					({selectedRecipe.yeast_temp_min.toFixed(0)}-{selectedRecipe.yeast_temp_max.toFixed(
						0
					)}°C)
				{/if}
			</p>
		{/if}
	</div>
{/if}
```

Add CSS for recipe reference:
```css
.recipe-reference {
	padding: var(--space-3);
	background: var(--recipe-accent-muted);
	border: 1px solid var(--recipe-accent-border);
	border-radius: 6px;
}

.reference-label {
	font-size: 12px;
	font-weight: 500;
	color: var(--recipe-accent);
	margin: 0 0 var(--space-1) 0;
	text-transform: uppercase;
	letter-spacing: 0.05em;
}

.reference-text {
	font-size: 13px;
	color: var(--text-secondary);
	font-family: var(--font-mono);
	margin: 0;
}
```

**Step 3: Test batch form integration**

Navigate to: http://localhost:5173/batches/new

Expected: Shows recipe selector at top, can select recipe, form auto-fills

**Step 4: Commit**

```bash
git add frontend/src/lib/components/RecipeSelector.svelte frontend/src/lib/components/BatchForm.svelte
git commit -m "feat: integrate recipe selector into batch form

- RecipeSelector component with search and selection
- Auto-fill batch name and measured OG from recipe
- Display yeast info as reference
- Optional selection, can clear

Part of #32"
```

---

## Task 9: Handle Recipe Query Parameter in Batch Form

**Files:**
- Modify: `frontend/src/routes/batches/new/+page.svelte`
- Modify: `frontend/src/lib/components/BatchForm.svelte`

**Step 1: Update BatchForm to accept initial recipe ID**

In `frontend/src/lib/components/BatchForm.svelte`, add prop:

```typescript
interface Props {
	onSubmit: (data: BatchCreate) => void | Promise<void>;
	onCancel: () => void;
	initialRecipeId?: number;  // ADD THIS
}

let { onSubmit, onCancel, initialRecipeId }: Props = $props();
```

Pass to RecipeSelector:
```svelte
<RecipeSelector
	selectedRecipeId={selectedRecipe?.id ?? initialRecipeId}
	onSelect={handleRecipeSelect}
/>
```

**Step 2: Update batch/new page to read query param**

In `frontend/src/routes/batches/new/+page.svelte`, add:

```typescript
import { page } from '$app/stores';

let recipeId = $derived(
	$page.url.searchParams.get('recipe_id')
		? parseInt($page.url.searchParams.get('recipe_id')!, 10)
		: undefined
);
```

Pass to BatchForm:
```svelte
<BatchForm onSubmit={handleSubmit} onCancel={handleCancel} initialRecipeId={recipeId} />
```

**Step 3: Test recipe → batch flow**

1. Navigate to recipe detail page
2. Click "Brew This Recipe"
3. Should redirect to `/batches/new?recipe_id=1`
4. Batch form should auto-select and pre-fill from recipe

Expected: Complete flow from recipe to batch creation works

**Step 4: Commit**

```bash
git add frontend/src/routes/batches/new/+page.svelte frontend/src/lib/components/BatchForm.svelte
git commit -m "feat: support recipe_id query parameter in batch creation

- Read recipe_id from URL query params
- Pass to BatchForm as initialRecipeId
- Auto-select recipe when navigating from recipe detail
- Completes recipe → batch creation flow

Part of #32"
```

---

## Task 10: Update CHANGELOG and Close Issue

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Add recipe UI to CHANGELOG**

In `CHANGELOG.md`, add under `## [Unreleased]`:

```markdown
### Added
- Recipe library UI for BeerXML import and management (#32)
  - Import page with drag-and-drop BeerXML file upload
  - Recipe list with search and filter
  - Recipe detail view with fermentation-focused layout
  - Laboratory notebook aesthetic with amber accents
  - Integration with batch creation (auto-fill from recipe)
  - Crimson Pro serif font for recipe names
  - JetBrains Mono for measurements
```

**Step 2: Verify all features work end-to-end**

Manual test checklist:
- [ ] Navigate to /recipes (empty state)
- [ ] Click Import Recipe
- [ ] Drag-and-drop valid BeerXML file
- [ ] Recipe appears in list
- [ ] Click recipe card → detail view
- [ ] Click "Brew This Recipe" → batch form pre-filled
- [ ] Create batch successfully
- [ ] Delete recipe with confirmation

Run: Test each step manually

Expected: All features work smoothly

**Step 3: Commit CHANGELOG**

```bash
git add CHANGELOG.md
git commit -m "docs: update CHANGELOG for recipe UI feature

Part of #32"
```

**Step 4: Create implementation summary**

The implementation is complete! Here's what was built:

**Routes Created:**
- `/recipes` - Recipe library list
- `/recipes/import` - BeerXML file upload
- `/recipes/[id]` - Recipe detail view

**Components Created:**
- `RecipeCard.svelte` - Recipe grid card with specimen box aesthetic
- `RecipeSelector.svelte` - Recipe picker for batch form

**API Integration:**
- `fetchRecipes()` - List all recipes
- `fetchRecipe(id)` - Get single recipe
- `importBeerXML(file)` - Upload BeerXML file
- `deleteRecipe(id)` - Remove recipe

**Design System:**
- Crimson Pro serif for recipe names (warmth, editorial)
- JetBrains Mono for measurements (precision)
- Amber accent color (`#f59e0b`) for recipe UI
- Laboratory notebook aesthetic

**Integration:**
- Recipe selector in batch creation form
- Auto-fill batch from recipe (name, OG, yeast)
- Query parameter support (`/batches/new?recipe_id=1`)
- Navigation link added to main menu

**All tasks complete!** Ready to test full workflow and close #32.

---

## Summary

This plan implements the complete recipe UI for BrewSignal:

1. **Task 1-2**: Foundation (fonts, colors, API functions)
2. **Task 3-4**: Core pages (RecipeCard component, recipe list)
3. **Task 5-6**: Import and detail pages
4. **Task 7**: Navigation integration
5. **Task 8-9**: Batch form integration with auto-fill
6. **Task 10**: Documentation and verification

**Expected Timeline:** ~3-4 hours for experienced developer with zero codebase context

**Tech Stack:** SvelteKit, TypeScript, Svelte 5 runes, CSS variables, existing SQLite backend

**Design:** Laboratory notebook aesthetic, amber accents, Crimson Pro + JetBrains Mono fonts
