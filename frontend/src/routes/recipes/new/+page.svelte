<script lang="ts">
	import { goto } from '$app/navigation';
	import type { RecipeCreate, RecipeUpdateData } from '$lib/api';
	import { createRecipe } from '$lib/api';
	import RecipeForm from '$lib/components/RecipeForm.svelte';

	let submitting = $state(false);
	let error = $state<string | null>(null);

	async function handleSubmit(data: RecipeCreate | RecipeUpdateData) {
		submitting = true;
		error = null;

		try {
			const recipe = await createRecipe(data as RecipeCreate);
			goto(`/recipes/${recipe.id}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to create recipe';
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
		background: var(--error-bg);
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
