<script lang="ts">
	import { goto } from '$app/navigation';
	import type { RecipeCreate } from '$lib/api';
	import { createRecipe } from '$lib/api';
	import RecipeBuilder from '$lib/components/recipe/RecipeBuilder.svelte';
	import type { RecipeData } from '$lib/components/recipe/RecipeBuilder.svelte';

	let submitting = $state(false);
	let error = $state<string | null>(null);
	let recipeBuilder: ReturnType<typeof RecipeBuilder> | undefined = $state();
	let reviewLoading = $state(false);

	// Poll review loading state from component
	$effect(() => {
		const interval = setInterval(() => {
			if (recipeBuilder) {
				reviewLoading = recipeBuilder.getReviewLoading();
			}
		}, 100);
		return () => clearInterval(interval);
	});

	async function handleSave(data: RecipeData) {
		submitting = true;
		error = null;

		try {
			// Convert RecipeBuilder output to RecipeCreate format
			const recipeCreate: RecipeCreate = {
				name: data.name,
				author: data.author || undefined,
				type: data.type || undefined,
				batch_size_liters: data.batch_size_liters,
				efficiency_percent: data.efficiency_percent,
				boil_time_minutes: data.boil_time_minutes,
				og: data.og,
				fg: data.fg,
				abv: data.abv,
				ibu: data.ibu,
				color_srm: data.color_srm,
				notes: data.notes || undefined,
				// Yeast details
				yeast_name: data.yeast?.name,
				yeast_lab: data.yeast?.producer,
				yeast_product_id: data.yeast?.product_id,
				yeast_temp_min: data.yeast?.temp_low ?? undefined,
				yeast_temp_max: data.yeast?.temp_high ?? undefined,
				yeast_attenuation:
					data.yeast?.attenuation_low && data.yeast?.attenuation_high
						? (data.yeast.attenuation_low + data.yeast.attenuation_high) / 2
						: undefined,
				// Store ingredient details for future retrieval
				format_extensions: {
					fermentables: data.fermentables.map((f) => ({
						id: f.id,
						name: f.name,
						amount_kg: f.amount_kg,
						color_lovibond: f.color_lovibond,
						potential_sg: f.potential_sg,
						type: f.type,
						origin: f.origin,
						maltster: f.maltster
					})),
					hops: data.hops.map((h) => ({
						id: h.id,
						name: h.name,
						amount_grams: h.amount_grams,
						alpha_acid_percent: h.alpha_acid_percent,
						boil_time_minutes: h.boil_time_minutes,
						use: h.use,
						form: h.form,
						origin: h.origin,
						purpose: h.purpose
					}))
				}
			};

			const recipe = await createRecipe(recipeCreate);
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
		<div class="header-content">
			<h1 class="page-title">Create New Recipe</h1>
			<p class="page-description">
				Build your recipe with real-time calculations, or
				<a href="/recipes/import" class="import-link">import from BeerXML/BeerJSON</a>
			</p>
		</div>
		<div class="header-actions">
			<button type="button" class="btn-ghost" onclick={handleCancel}>Cancel</button>
			<button
				type="button"
				class="btn-review"
				onclick={() => recipeBuilder?.review()}
				disabled={reviewLoading}
			>
				{#if reviewLoading}
					<span class="btn-spinner"></span>
					Analyzing...
				{:else}
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
					</svg>
					AI Review
				{/if}
			</button>
			<button
				type="button"
				class="btn-save"
				onclick={() => recipeBuilder?.save()}
				disabled={submitting}
			>
				{#if submitting}
					<span class="btn-spinner"></span>
					Saving...
				{:else}
					Save Recipe
				{/if}
			</button>
		</div>
	</div>

	{#if error}
		<div class="error-banner">
			<svg
				class="error-icon"
				fill="none"
				viewBox="0 0 24 24"
				stroke="currentColor"
				stroke-width="2"
			>
				<path
					stroke-linecap="round"
					stroke-linejoin="round"
					d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
				/>
			</svg>
			<span>{error}</span>
		</div>
	{/if}

	{#if submitting}
		<div class="saving-overlay">
			<div class="spinner"></div>
			<span>Saving recipe...</span>
		</div>
	{/if}

	<RecipeBuilder bind:this={recipeBuilder} onSave={handleSave} onCancel={handleCancel} />
</div>

<style>
	.page-container {
		max-width: 1200px;
		margin: 0 auto;
		padding: var(--space-6);
		position: relative;
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
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-4);
		margin-bottom: var(--space-6);
		padding-bottom: var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
	}

	.header-content {
		flex: 1;
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

	/* Header Actions */
	.header-actions {
		display: flex;
		gap: var(--space-3);
		align-items: center;
		flex-shrink: 0;
	}

	.btn-ghost,
	.btn-review,
	.btn-save {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-4);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.15s ease;
		white-space: nowrap;
	}

	.btn-ghost {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-secondary);
	}

	.btn-ghost:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
		border-color: var(--border-hover);
	}

	.btn-review {
		background: transparent;
		border: 1px solid var(--positive, #10b981);
		color: var(--positive, #10b981);
	}

	.btn-review:hover:not(:disabled) {
		background: var(--positive, #10b981);
		color: var(--bg-base);
	}

	.btn-review:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-save {
		background: var(--recipe-accent, #f59e0b);
		border: none;
		color: var(--bg-base);
	}

	.btn-save:hover:not(:disabled) {
		background: color-mix(in srgb, var(--recipe-accent, #f59e0b) 85%, white);
	}

	.btn-save:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.btn-icon {
		width: 16px;
		height: 16px;
	}

	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
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

	.saving-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-4);
		z-index: 1000;
		color: white;
		font-size: 16px;
	}

	.spinner {
		width: 40px;
		height: 40px;
		border: 3px solid rgba(255, 255, 255, 0.3);
		border-top-color: var(--recipe-accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
</style>
