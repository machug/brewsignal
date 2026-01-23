<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse, RecipeUpdateData } from '$lib/api';
	import { fetchRecipe, updateRecipe } from '$lib/api';
	import RecipeBuilder from '$lib/components/recipe/RecipeBuilder.svelte';
	import type { RecipeData } from '$lib/components/recipe/RecipeBuilder.svelte';
	import { srmToHex, srmToDescription, calculateBUGU } from '$lib/brewing';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let submitting = $state(false);
	let recipeBuilder: ReturnType<typeof RecipeBuilder> | undefined = $state();
	let reviewLoading = $state(false);

	let recipeId = $derived.by(() => {
		const id = parseInt($page.params.id || '', 10);
		return isNaN(id) || id <= 0 ? null : id;
	});

	// Derived stats (matching detail page)
	let srmColor = $derived(recipe?.color_srm ? srmToHex(recipe.color_srm) : null);
	let srmDesc = $derived(recipe?.color_srm ? srmToDescription(recipe.color_srm) : null);
	let bugu = $derived(recipe?.ibu && recipe?.og ? calculateBUGU(recipe.ibu, recipe.og) : null);

	// Poll review loading state from component
	$effect(() => {
		const interval = setInterval(() => {
			if (recipeBuilder) {
				reviewLoading = recipeBuilder.getReviewLoading();
			}
		}, 100);
		return () => clearInterval(interval);
	});

	onMount(async () => {
		if (!recipeId) {
			loading = false;
			goto('/recipes');
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

	async function handleSave(data: RecipeData) {
		if (!recipeId) return;

		submitting = true;
		error = null;

		try {
			// Convert RecipeBuilder output to RecipeUpdateData format
			const recipeUpdate: RecipeUpdateData = {
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

			await updateRecipe(recipeId, recipeUpdate);
			goto(`/recipes/${recipeId}`);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to update recipe';
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
			<div class="header-content">
				<h1 class="page-title">Edit Recipe</h1>
				<p class="page-description">Editing: {recipe.name}</p>
			</div>
			<div class="header-actions">
				<button type="button" class="btn-ghost" onclick={handleCancel}>Cancel</button>
				<span class="action-divider"></span>
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
						Save Changes
					{/if}
				</button>
			</div>
		</div>

		{#if error}
			<div class="error-banner">
				<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<span class="error-text">{error}</span>
				<button class="error-dismiss" onclick={() => (error = null)} aria-label="Dismiss error">
					<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
					</svg>
				</button>
			</div>
		{/if}

		{#if submitting}
			<div class="saving-overlay">
				<div class="spinner-large"></div>
				<span>Saving recipe...</span>
			</div>
		{/if}

		<RecipeBuilder
			bind:this={recipeBuilder}
			initialData={recipe}
			onSave={handleSave}
			onCancel={handleCancel}
		/>
	{/if}
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

	/* Header Actions */
	.header-actions {
		display: flex;
		gap: var(--space-3);
		align-items: center;
		flex-shrink: 0;
	}

	.action-divider {
		width: 1px;
		height: 24px;
		background: var(--border-subtle, rgba(255, 255, 255, 0.08));
		margin: 0 var(--space-1);
	}

	/* Button Base Styles */
	.btn-ghost,
	.btn-review,
	.btn-save {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-2);
		border-radius: 8px;
		font-weight: 500;
		cursor: pointer;
		transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
		white-space: nowrap;
	}

	/* Cancel - Tertiary/Ghost */
	.btn-ghost {
		padding: 8px 14px;
		font-size: 13px;
		background: transparent;
		border: 1px solid transparent;
		color: var(--text-muted);
	}

	.btn-ghost:hover {
		background: rgba(255, 255, 255, 0.04);
		color: var(--text-secondary);
	}

	/* AI Review - Secondary */
	.btn-review {
		padding: 9px 16px;
		font-size: 13px;
		background: rgba(16, 185, 129, 0.08);
		border: 1px solid rgba(16, 185, 129, 0.3);
		color: var(--positive);
	}

	.btn-review:hover:not(:disabled) {
		background: rgba(16, 185, 129, 0.15);
		border-color: rgba(16, 185, 129, 0.5);
		transform: translateY(-1px);
	}

	.btn-review:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Save - Primary */
	.btn-save {
		padding: 10px 22px;
		font-size: 14px;
		font-weight: 600;
		background: linear-gradient(135deg, var(--recipe-accent) 0%, var(--recipe-accent-hover) 100%);
		border: none;
		color: var(--gray-950);
		box-shadow:
			0 2px 8px var(--recipe-accent-border),
			0 1px 2px rgba(0, 0, 0, 0.2),
			inset 0 1px 0 rgba(255, 255, 255, 0.15);
		text-shadow: 0 1px 0 rgba(255, 255, 255, 0.1);
	}

	.btn-save:hover:not(:disabled) {
		background: linear-gradient(135deg, var(--tilt-yellow) 0%, var(--recipe-accent) 100%);
		box-shadow:
			0 4px 12px var(--recipe-accent-border),
			0 2px 4px rgba(0, 0, 0, 0.2),
			inset 0 1px 0 rgba(255, 255, 255, 0.2);
		transform: translateY(-1px);
	}

	.btn-save:active:not(:disabled) {
		transform: translateY(0);
		box-shadow:
			0 1px 4px rgba(245, 158, 11, 0.3),
			inset 0 1px 2px rgba(0, 0, 0, 0.1);
	}

	.btn-save:disabled {
		opacity: 0.5;
		cursor: not-allowed;
		box-shadow: none;
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

	.spinner-large {
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

	.error-message {
		color: var(--negative);
		font-size: 14px;
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

	.error-text {
		flex: 1;
	}

	.error-dismiss {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		padding: 0;
		background: transparent;
		border: none;
		border-radius: 4px;
		color: var(--negative);
		cursor: pointer;
		opacity: 0.7;
		transition: opacity 0.15s ease, background 0.15s ease;
		flex-shrink: 0;
	}

	.error-dismiss:hover {
		opacity: 1;
		background: rgba(239, 68, 68, 0.1);
	}

	.error-dismiss svg {
		width: 16px;
		height: 16px;
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
</style>
