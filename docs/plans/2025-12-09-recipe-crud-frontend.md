# Recipe CRUD Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the recipe management frontend UI by adding create/edit forms and updating existing pages to use BeerJSON 2.06 field names.

**Architecture:** Extend existing recipe pages with comprehensive create/edit forms. Update field names from legacy BeerXML (og_target, fg_target) to BeerJSON standard (og, fg). Build multi-step forms for recipe creation with ingredients, fermentation schedule, and metadata.

**Tech Stack:** SvelteKit 5 (runes), TailwindCSS v4, TypeScript, existing API helpers

**Beads Issue:** tilt_ui-pzu

---

## Context

**What Already Exists:**
- ✅ Recipe list page (`/recipes`) - functional but uses old field names
- ✅ Recipe detail page (`/recipes/[id]`) - functional but uses old field names
- ✅ Recipe import page (`/recipes/import`) - fully functional
- ✅ API functions: `fetchRecipes()`, `fetchRecipe()`, `createRecipe()`, `updateRecipe()`, `importRecipe()`, `deleteRecipe()`
- ✅ Backend CRUD endpoints with BeerJSON schema validation
- ✅ Components: `RecipeCard`, `RecipeSelector`, `FermentablesList`, `HopSchedule`

**What's Missing:**
- ❌ Recipe create/edit forms
- ❌ BeerJSON field name migration (og_target → og, etc.)
- ❌ Edit button/route on detail page
- ❌ Manual recipe creation flow

**Backend Field Names (BeerJSON 2.06):**
- `og` (NOT `og_target`)
- `fg` (NOT `fg_target`)
- `abv` (NOT `abv_target`)
- `color_srm` (NOT `srm_target`)
- `batch_size_liters` (NOT `batch_size`)
- `cultures` (NOT `yeasts`)

---

## Task 1: Update Recipe Detail Page Field Names

**Files:**
- Modify: `frontend/src/routes/recipes/[id]/+page.svelte:107-186`

**Step 1: Update OG/FG/ABV field references**

Find and replace in the recipe detail page:
- `recipe.og_target` → `recipe.og`
- `recipe.fg_target` → `recipe.fg`
- `recipe.abv_target` → `recipe.abv`
- `recipe.srm_target` → `recipe.color_srm`
- `recipe.ibu_target` → `recipe.ibu`
- `recipe.batch_size` → `recipe.batch_size_liters`

**Step 2: Test the detail page**

```bash
# Start dev server
cd frontend && npm run dev
```

1. Navigate to http://localhost:5173/recipes
2. Click on any recipe
3. Verify all fields display correctly
4. Verify no console errors

Expected: All recipe parameters display with correct values

**Step 3: Commit**

```bash
git add frontend/src/routes/recipes/\[id\]/+page.svelte
git commit -m "fix: update recipe detail page to use BeerJSON field names

- Change og_target/fg_target/abv_target to og/fg/abv
- Change srm_target to color_srm
- Change batch_size to batch_size_liters
- Align with BeerJSON 2.06 schema from PR #87

Related: tilt_ui-pzu"
```

---

## Task 2: Create Recipe Form Component

**Files:**
- Create: `frontend/src/lib/components/RecipeForm.svelte`

**Step 1: Write the RecipeForm component scaffold**

```svelte
<script lang="ts">
	import type { RecipeCreate, RecipeUpdate } from '$lib/api';

	interface Props {
		recipe?: RecipeUpdate;
		onSubmit: (data: RecipeCreate | RecipeUpdate) => Promise<void>;
		onCancel: () => void;
		submitting?: boolean;
	}

	let { recipe, onSubmit, onCancel, submitting = false }: Props = $props();

	// Form state
	let name = $state(recipe?.name || '');
	let author = $state(recipe?.author || '');
	let type = $state(recipe?.type || '');
	let batch_size_liters = $state(recipe?.batch_size_liters || 19);
	let og = $state(recipe?.og || 1.050);
	let fg = $state(recipe?.fg || 1.010);
	let abv = $state(recipe?.abv || 5.0);
	let ibu = $state(recipe?.ibu || 30);
	let color_srm = $state(recipe?.color_srm || 10);
	let notes = $state(recipe?.notes || '');

	async function handleSubmit(e: Event) {
		e.preventDefault();

		const data: RecipeCreate | RecipeUpdate = {
			name,
			author: author || undefined,
			type: type || undefined,
			batch_size_liters,
			og,
			fg,
			abv,
			ibu: ibu || undefined,
			color_srm: color_srm || undefined,
			notes: notes || undefined
		};

		await onSubmit(data);
	}
</script>

<form on:submit={handleSubmit} class="recipe-form">
	<div class="form-section">
		<h2 class="section-title">Basic Information</h2>

		<div class="form-row">
			<label class="form-label">
				Recipe Name *
				<input
					type="text"
					bind:value={name}
					required
					class="form-input"
					placeholder="e.g., Philter XPA Clone"
				/>
			</label>
		</div>

		<div class="form-row">
			<label class="form-label">
				Brewer
				<input
					type="text"
					bind:value={author}
					class="form-input"
					placeholder="Your name"
				/>
			</label>

			<label class="form-label">
				Style
				<input
					type="text"
					bind:value={type}
					class="form-input"
					placeholder="e.g., American Pale Ale"
				/>
			</label>
		</div>
	</div>

	<div class="form-section">
		<h2 class="section-title">Batch Details</h2>

		<div class="form-row">
			<label class="form-label">
				Batch Size (L) *
				<input
					type="number"
					bind:value={batch_size_liters}
					required
					step="0.1"
					min="0"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				Color (SRM)
				<input
					type="number"
					bind:value={color_srm}
					step="0.1"
					min="0"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				Bitterness (IBU)
				<input
					type="number"
					bind:value={ibu}
					step="1"
					min="0"
					class="form-input"
				/>
			</label>
		</div>
	</div>

	<div class="form-section">
		<h2 class="section-title">Fermentation Targets</h2>

		<div class="form-row">
			<label class="form-label">
				Original Gravity *
				<input
					type="number"
					bind:value={og}
					required
					step="0.001"
					min="1.000"
					max="1.200"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				Final Gravity *
				<input
					type="number"
					bind:value={fg}
					required
					step="0.001"
					min="1.000"
					max="1.200"
					class="form-input"
				/>
			</label>

			<label class="form-label">
				ABV (%) *
				<input
					type="number"
					bind:value={abv}
					required
					step="0.1"
					min="0"
					max="20"
					class="form-input"
				/>
			</label>
		</div>
	</div>

	<div class="form-section">
		<h2 class="section-title">Notes</h2>

		<label class="form-label">
			Brewing Notes
			<textarea
				bind:value={notes}
				rows="4"
				class="form-textarea"
				placeholder="Optional brewing notes, tips, or variations..."
			/>
		</label>
	</div>

	<div class="form-actions">
		<button
			type="button"
			onclick={onCancel}
			class="btn-secondary"
			disabled={submitting}
		>
			Cancel
		</button>
		<button
			type="submit"
			class="btn-primary"
			disabled={submitting}
		>
			{submitting ? 'Saving...' : recipe ? 'Update Recipe' : 'Create Recipe'}
		</button>
	</div>
</form>

<style>
	.recipe-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-8);
		max-width: 800px;
	}

	.form-section {
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

	.form-row {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: var(--space-4);
	}

	.form-label {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.form-input,
	.form-textarea {
		width: 100%;
		padding: var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
		font-family: var(--font-sans);
		transition: border-color var(--transition);
	}

	.form-input:focus,
	.form-textarea:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.form-textarea {
		resize: vertical;
		min-height: 80px;
	}

	.form-actions {
		display: flex;
		gap: var(--space-3);
		justify-content: flex-end;
		padding-top: var(--space-4);
		border-top: 1px solid var(--border-subtle);
	}

	.btn-secondary,
	.btn-primary {
		padding: var(--space-3) var(--space-6);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
		border: none;
	}

	.btn-secondary {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.btn-secondary:hover:not(:disabled) {
		background: var(--bg-hover);
	}

	.btn-primary {
		background: var(--recipe-accent);
		color: white;
	}

	.btn-primary:hover:not(:disabled) {
		background: var(--recipe-accent-hover);
	}

	.btn-secondary:disabled,
	.btn-primary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}
</style>
```

**Step 2: Test the component (visual verification)**

Create a test page temporarily:

```bash
# Create test file
cat > frontend/src/routes/test-form/+page.svelte << 'EOF'
<script>
	import RecipeForm from '$lib/components/RecipeForm.svelte';

	function handleSubmit(data) {
		console.log('Form submitted:', data);
		return Promise.resolve();
	}

	function handleCancel() {
		console.log('Cancelled');
	}
</script>

<RecipeForm onSubmit={handleSubmit} onCancel={handleCancel} />
EOF
```

Navigate to http://localhost:5173/test-form and verify:
- Form renders without errors
- All fields are editable
- Required fields show asterisks
- Cancel button works (logs to console)
- Submit logs data to console

**Step 3: Remove test page and commit**

```bash
rm -rf frontend/src/routes/test-form
git add frontend/src/lib/components/RecipeForm.svelte
git commit -m "feat: add RecipeForm component for recipe create/edit

- Support both create and update modes
- BeerJSON 2.06 field names (og, fg, abv, color_srm, batch_size_liters)
- Basic recipe fields only (ingredients will be phase 2)
- Responsive form layout with validation

Related: tilt_ui-pzu"
```

---

## Task 3: Create New Recipe Page

**Files:**
- Create: `frontend/src/routes/recipes/new/+page.svelte`

**Step 1: Write the new recipe page**

```svelte
<script lang="ts">
	import { goto } from '$app/navigation';
	import type { RecipeCreate } from '$lib/api';
	import { createRecipe } from '$lib/api';
	import RecipeForm from '$lib/components/RecipeForm.svelte';

	let submitting = $state(false);
	let error = $state<string | null>(null);

	async function handleSubmit(data: RecipeCreate) {
		submitting = true;
		error = null;

		try {
			const recipe = await createRecipe(data);
			goto(`/recipes/${recipe.id}`);
		} catch (e) {
			if (e instanceof Error) {
				error = e.message;
			} else if (Array.isArray(e)) {
				// Handle array error format from backend
				error = e.join(', ');
			} else {
				error = 'Failed to create recipe';
			}
			submitting = false;
		}
	}

	function handleCancel() {
		goto('/recipes');
	}
</script>

<svelte:head>
	<title>New Recipe | BrewSignal</title>
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

	<div class="page-header">
		<h1 class="page-title">Create New Recipe</h1>
		<p class="page-description">
			Create a recipe manually or <a href="/recipes/import" class="import-link">import from BeerXML/BeerJSON</a>
		</p>
	</div>

	{#if error}
		<div class="error-banner">
			<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			<span>{error}</span>
		</div>
	{/if}

	<RecipeForm
		onSubmit={handleSubmit}
		onCancel={handleCancel}
		{submitting}
	/>
</div>

<style>
	.page-container {
		max-width: 900px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.back-link {
		margin-bottom: var(--space-4);
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

	.page-header {
		margin-bottom: var(--space-8);
		padding-bottom: var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
	}

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0 0 var(--space-2) 0;
		color: var(--text-primary);
	}

	.page-description {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.import-link {
		color: var(--recipe-accent);
		text-decoration: none;
		font-weight: 500;
	}

	.import-link:hover {
		text-decoration: underline;
	}

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-4);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid var(--negative);
		border-radius: 6px;
		color: var(--negative);
		margin-bottom: var(--space-6);
		font-size: 14px;
	}

	.error-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}
</style>
```

**Step 2: Add "New Recipe" button to recipe list page**

Edit `frontend/src/routes/recipes/+page.svelte`:

Find this button (around line 49):
```svelte
<a href="/recipes/import" class="import-btn">
```

Replace with a button group:
```svelte
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
```

Add styles:
```css
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
```

**Step 3: Test the new recipe flow**

```bash
cd frontend && npm run dev
```

1. Navigate to http://localhost:5173/recipes
2. Click "New Recipe" button
3. Fill in form:
   - Name: "Test IPA"
   - Batch Size: 20
   - OG: 1.060
   - FG: 1.012
   - ABV: 6.3
4. Click "Create Recipe"
5. Verify redirect to recipe detail page
6. Verify all fields display correctly

Expected: Recipe created successfully, displays on detail page

**Step 4: Commit**

```bash
git add frontend/src/routes/recipes/new/+page.svelte frontend/src/routes/recipes/+page.svelte
git commit -m "feat: add new recipe creation page

- Create /recipes/new route with RecipeForm
- Add \"New Recipe\" button to recipes list
- Handle creation errors (string and array formats)
- Redirect to detail page on success

Related: tilt_ui-pzu"
```

---

## Task 4: Create Recipe Edit Page

**Files:**
- Create: `frontend/src/routes/recipes/[id]/edit/+page.svelte`

**Step 1: Write the edit recipe page**

```svelte
<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse, RecipeUpdate } from '$lib/api';
	import { fetchRecipe, updateRecipe } from '$lib/api';
	import RecipeForm from '$lib/components/RecipeForm.svelte';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let submitting = $state(false);

	let recipeId = $derived.by(() => {
		const id = parseInt($page.params.id || '', 10);
		return isNaN(id) || id <= 0 ? null : id;
	});

	onMount(async () => {
		if (!recipeId) {
			error = 'Invalid recipe ID';
			loading = false;
			return;
		}

		try {
			recipe = await fetchRecipe(recipeId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load recipe';
		} finally {
			loading = false;
		}
	});

	async function handleSubmit(data: RecipeUpdate) {
		if (!recipeId) return;

		submitting = true;
		error = null;

		try {
			await updateRecipe(recipeId, data);
			goto(`/recipes/${recipeId}`);
		} catch (e) {
			if (e instanceof Error) {
				error = e.message;
			} else if (Array.isArray(e)) {
				error = e.join(', ');
			} else {
				error = 'Failed to update recipe';
			}
			submitting = false;
		}
	}

	function handleCancel() {
		if (recipeId) {
			goto(`/recipes/${recipeId}`);
		} else {
			goto('/recipes');
		}
	}
</script>

<svelte:head>
	<title>Edit {recipe?.name || 'Recipe'} | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="back-link">
		<a href="/recipes/{recipeId}" class="back-btn">
			<svg class="back-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7" />
			</svg>
			Back to Recipe
		</a>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading recipe...</p>
		</div>
	{:else if error && !recipe}
		<div class="error-state">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipe}
		<div class="page-header">
			<h1 class="page-title">Edit Recipe</h1>
			<p class="page-description">Editing: {recipe.name}</p>
		</div>

		{#if error}
			<div class="error-banner">
				<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<span>{error}</span>
			</div>
		{/if}

		<RecipeForm
			recipe={recipe}
			onSubmit={handleSubmit}
			onCancel={handleCancel}
			{submitting}
		/>
	{/if}
</div>

<style>
	.page-container {
		max-width: 900px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.back-link {
		margin-bottom: var(--space-4);
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

	.page-header {
		margin-bottom: var(--space-8);
		padding-bottom: var(--space-6);
		border-bottom: 1px solid var(--border-subtle);
	}

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0 0 var(--space-2) 0;
		color: var(--text-primary);
	}

	.page-description {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
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

	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-4);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid var(--negative);
		border-radius: 6px;
		color: var(--negative);
		margin-bottom: var(--space-6);
		font-size: 14px;
	}

	.error-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}
</style>
```

**Step 2: Add Edit button to recipe detail page**

Edit `frontend/src/routes/recipes/[id]/+page.svelte` around line 92:

Replace the delete button section with a button group:
```svelte
<div class="header-actions">
	<a href="/recipes/{recipe.id}/edit" class="edit-btn">
		<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
			<path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
		</svg>
		Edit
	</a>
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
```

Add styles after `.delete-btn`:
```css
.header-actions {
	display: flex;
	gap: var(--space-2);
}

.edit-btn {
	display: inline-flex;
	align-items: center;
	gap: var(--space-2);
	padding: var(--space-2) var(--space-3);
	background: transparent;
	border: 1px solid var(--border-default);
	border-radius: 6px;
	color: var(--text-secondary);
	font-size: 14px;
	text-decoration: none;
	cursor: pointer;
	transition: all var(--transition);
}

.edit-btn:hover {
	border-color: var(--recipe-accent);
	color: var(--recipe-accent);
}
```

**Step 3: Test the edit flow**

```bash
cd frontend && npm run dev
```

1. Navigate to http://localhost:5173/recipes
2. Click on any recipe
3. Click "Edit" button
4. Modify a field (e.g., change name)
5. Click "Update Recipe"
6. Verify redirect back to detail page
7. Verify changes are saved

Expected: Recipe updates successfully

**Step 4: Commit**

```bash
git add frontend/src/routes/recipes/\[id\]/edit/+page.svelte frontend/src/routes/recipes/\[id\]/+page.svelte
git commit -m "feat: add recipe edit page

- Create /recipes/[id]/edit route with RecipeForm
- Add \"Edit\" button to recipe detail page
- Load existing recipe data into form
- Handle update errors (string and array formats)

Related: tilt_ui-pzu"
```

---

## Task 5: Final Testing & Documentation

**Step 1: Run full integration test**

```bash
cd frontend && npm run dev
```

Test complete CRUD flow:
1. **Create**: /recipes/new → create "Integration Test Recipe"
2. **Read**: /recipes → verify appears in list
3. **Read**: /recipes/{id} → verify all fields display
4. **Update**: /recipes/{id}/edit → change name to "Updated Recipe"
5. **Delete**: /recipes/{id} → click Delete → confirm

Expected: All CRUD operations work without errors

**Step 2: Run TypeScript type check**

```bash
cd frontend && npm run check
```

Expected: No new type errors (pre-existing a11y warnings are OK)

**Step 3: Update CHANGELOG**

Edit `CHANGELOG.md`, add new entry at top:

```markdown
## [Unreleased]

### Added
- Recipe CRUD frontend UI (tilt_ui-pzu)
  - Manual recipe creation form with BeerJSON fields
  - Recipe edit functionality
  - Updated recipe detail page with BeerJSON field names (og, fg, abv, color_srm)
  - "New Recipe" and "Edit" buttons in navigation flow
```

**Step 4: Update Beads issue**

```bash
bd update tilt_ui-pzu --status=closed
bd sync
```

**Step 5: Final commit**

```bash
git add CHANGELOG.md
git commit -m "docs: update changelog for recipe CRUD frontend

Related: tilt_ui-pzu"
```

---

## Completion Checklist

- [ ] Task 1: Recipe detail page uses BeerJSON field names
- [ ] Task 2: RecipeForm component created and tested
- [ ] Task 3: New recipe page functional
- [ ] Task 4: Edit recipe page functional
- [ ] Task 5: Integration tests pass, changelog updated, Beads issue closed

---

## Future Enhancements (Out of Scope)

These were in the original Beads issue but are deferred:
- Ingredients editor (fermentables, hops, cultures, misc)
- Mash/fermentation/packaging steps editor
- BeerJSON format_extensions editor
- Sort/filter controls on recipe list page
- Recipe clone functionality
