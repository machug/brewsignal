<script lang="ts">
	import { recipeUrl } from '$lib/urls';
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
				style_id: data.style_id,
				style: data.style,
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
						purpose: h.purpose,
						// Persist extract metadata so it round-trips through
						// format_extensions. amount_ml is meaningful only when
						// is_extract is true.
						is_extract: Boolean(h.is_extract),
						amount_ml: h.is_extract ? h.amount_ml ?? null : null
					}))
				}
			};

			const recipe = await createRecipe(recipeCreate);
			goto(recipeUrl(recipe));
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
			<span class="error-message">{error}</span>
			<button class="error-dismiss" onclick={() => (error = null)} aria-label="Dismiss error">
				<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
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
		max-width: 1280px;
		margin: 0 auto;
		padding: var(--space-lg);
		position: relative;
	}

	.back-link {
		margin-bottom: var(--space-md);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
		min-height: 44px;
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
		text-decoration: none;
		transition: color var(--transition);
	}

	.back-btn:hover {
		color: var(--ink-primary);
	}

	.back-icon {
		width: 16px;
		height: 16px;
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-md);
		flex-wrap: wrap;
		margin-bottom: var(--space-lg);
		padding-bottom: var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.header-content {
		flex: 1 1 280px;
		min-width: 0;
	}

	.page-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 600;
		letter-spacing: -0.01em;
		line-height: 1.2;
		margin: 0 0 var(--space-xs) 0;
		color: var(--ink-primary);
	}

	.page-description {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: 0;
		overflow-wrap: anywhere;
	}

	.import-link {
		color: var(--ink-primary);
		font-weight: 600;
		text-decoration: underline;
		text-decoration-color: var(--accent-rule);
		text-underline-offset: 3px;
	}

	.import-link:hover {
		text-decoration-color: var(--accent);
	}

	/* Header actions: accent only on the primary (save) action */
	.header-actions {
		display: flex;
		gap: var(--space-xs);
		align-items: center;
		flex-wrap: wrap;
	}

	.action-divider {
		width: 1px;
		height: 24px;
		background: var(--rule-hairline);
	}

	.btn-ghost,
	.btn-review,
	.btn-save {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		min-height: 44px;
		padding: var(--space-xs) var(--space-md);
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		white-space: nowrap;
		border-radius: 4px;
		cursor: pointer;
		transition: background var(--transition), border-color var(--transition), color var(--transition);
	}

	.btn-ghost {
		background: transparent;
		border: 1px solid transparent;
		color: var(--ink-secondary);
	}

	.btn-ghost:hover {
		border-color: var(--rule-strong);
		color: var(--ink-primary);
	}

	.btn-review {
		background: transparent;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}

	.btn-review:hover:not(:disabled) {
		border-color: var(--ink-secondary);
		color: var(--ink-primary);
	}

	.btn-save {
		background: var(--accent);
		border: 1px solid var(--accent);
		color: var(--accent-ink);
	}

	.btn-save:hover:not(:disabled) {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.btn-review:disabled,
	.btn-save:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-ghost:focus-visible,
	.btn-review:focus-visible,
	.btn-save:focus-visible,
	.back-btn:focus-visible,
	.import-link:focus-visible,
	.error-dismiss:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn-icon {
		width: 16px;
		height: 16px;
		flex-shrink: 0;
	}

	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	/* Errors: danger text plus outline plus icon, never colour alone */
	.error-banner {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--status-danger);
		border-radius: 4px;
		color: var(--status-danger);
		margin-bottom: var(--space-lg);
		font-size: var(--text-sm);
	}

	.error-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}

	.error-message {
		flex: 1;
		min-width: 0;
		overflow-wrap: anywhere;
	}

	.error-dismiss {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		margin: -10px -10px -10px 0;
		padding: 0;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 4px;
		color: var(--status-danger);
		cursor: pointer;
		flex-shrink: 0;
	}

	.error-dismiss:hover {
		border-color: var(--status-danger);
	}

	.error-dismiss svg {
		width: 16px;
		height: 16px;
	}

	.saving-overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in oklch, var(--bg-canvas) 80%, transparent);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		gap: var(--space-md);
		z-index: 1000;
		color: var(--ink-primary);
		font-size: var(--text-base);
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
		.spinner,
		.btn-spinner {
			animation-duration: 2.4s;
		}
	}

	@media (max-width: 760px) {
		.page-container {
			padding: var(--space-md);
		}

		.header-actions {
			width: 100%;
		}

		.action-divider {
			display: none;
		}

		.btn-review,
		.btn-save {
			flex: 1 1 0;
		}
	}
</style>
