<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse, RecipeUpdateData } from '$lib/api';
	import { fetchRecipe, updateRecipe } from '$lib/api';
	import RecipeBuilder from '$lib/components/recipe/RecipeBuilder.svelte';
	import type { RecipeData } from '$lib/components/recipe/RecipeBuilder.svelte';
	import { srmToHex, srmToDescription, calculateBUGU } from '$lib/brewing';
	// Nested collection editors
	import MashScheduleEditor from '$lib/components/recipe/MashScheduleEditor.svelte';
	import FermentationScheduleEditor from '$lib/components/recipe/FermentationScheduleEditor.svelte';
	import WaterProfileEditor from '$lib/components/recipe/WaterProfileEditor.svelte';
	import WaterAdjustmentEditor from '$lib/components/recipe/WaterAdjustmentEditor.svelte';
	import MiscEditor from '$lib/components/recipe/MiscEditor.svelte';
	import {
		updateRecipeMashSteps,
		updateRecipeFermentationSteps,
		updateRecipeWaterProfiles,
		updateRecipeWaterAdjustments,
		updateRecipeMiscs,
		type MashStepInput,
		type FermentationStepInput,
		type WaterProfileInput,
		type WaterAdjustmentInput,
		type MiscInput
	} from '$lib/api';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let submitting = $state(false);
	let recipeBuilder: ReturnType<typeof RecipeBuilder> | undefined = $state();
	let reviewLoading = $state(false);

	// State for nested collections
	let mashSteps = $state<MashStepInput[]>([]);
	let fermentationSteps = $state<FermentationStepInput[]>([]);
	let waterProfiles = $state<WaterProfileInput[]>([]);
	let waterAdjustments = $state<WaterAdjustmentInput[]>([]);
	let miscs = $state<MiscInput[]>([]);

	// Saving states for each collection
	let mashSaving = $state(false);
	let fermSaving = $state(false);
	let waterProfileSaving = $state(false);
	let waterAdjSaving = $state(false);
	let miscSaving = $state(false);

	// Save status feedback for each collection
	let mashSaveStatus = $state<'success' | 'error' | null>(null);
	let fermSaveStatus = $state<'success' | 'error' | null>(null);
	let waterProfileSaveStatus = $state<'success' | 'error' | null>(null);
	let waterAdjSaveStatus = $state<'success' | 'error' | null>(null);
	let miscSaveStatus = $state<'success' | 'error' | null>(null);

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

	// Initialize nested collections from recipe data
	$effect(() => {
		if (recipe) {
			mashSteps = (recipe.mash_steps || []).map((s) => ({
				step_number: s.step_number,
				name: s.name,
				type: s.type,
				temp_c: s.temp_c,
				time_minutes: s.time_minutes,
				infusion_amount_liters: s.infusion_amount_liters,
				infusion_temp_c: s.infusion_temp_c,
				ramp_time_minutes: s.ramp_time_minutes
			}));
			fermentationSteps = (recipe.fermentation_steps || []).map((s) => ({
				step_number: s.step_number,
				type: s.type,
				temp_c: s.temp_c,
				time_days: s.time_days
			}));
			waterProfiles = (recipe.water_profiles || []).map((p) => ({
				profile_type: p.profile_type,
				name: p.name,
				calcium_ppm: p.calcium_ppm,
				magnesium_ppm: p.magnesium_ppm,
				sodium_ppm: p.sodium_ppm,
				chloride_ppm: p.chloride_ppm,
				sulfate_ppm: p.sulfate_ppm,
				bicarbonate_ppm: p.bicarbonate_ppm,
				ph: p.ph,
				alkalinity: p.alkalinity
			}));
			waterAdjustments = (recipe.water_adjustments || []).map((a) => ({
				stage: a.stage,
				volume_liters: a.volume_liters,
				calcium_sulfate_g: a.calcium_sulfate_g,
				calcium_chloride_g: a.calcium_chloride_g,
				magnesium_sulfate_g: a.magnesium_sulfate_g,
				sodium_bicarbonate_g: a.sodium_bicarbonate_g,
				calcium_carbonate_g: a.calcium_carbonate_g,
				calcium_hydroxide_g: a.calcium_hydroxide_g,
				magnesium_chloride_g: a.magnesium_chloride_g,
				sodium_chloride_g: a.sodium_chloride_g,
				acid_type: a.acid_type,
				acid_ml: a.acid_ml,
				acid_concentration_percent: a.acid_concentration_percent
			}));
			miscs = (recipe.miscs || []).map((m) => ({
				name: m.name,
				type: m.type || 'other',
				use: m.use || 'boil',
				time_min: m.time_min,
				amount_kg: m.amount_kg,
				amount_unit: m.amount_unit,
				use_for: m.use_for,
				notes: m.notes
			}));
		}
	});

	// Save handlers for nested collections
	async function saveMashSteps() {
		if (!recipe) return;
		mashSaving = true;
		mashSaveStatus = null;
		try {
			await updateRecipeMashSteps(recipe.id, mashSteps);
			mashSaveStatus = 'success';
		} catch (e) {
			console.error('Failed to save mash steps', e);
			mashSaveStatus = 'error';
		} finally {
			mashSaving = false;
		}
	}

	async function saveFermentationSteps() {
		if (!recipe) return;
		fermSaving = true;
		fermSaveStatus = null;
		try {
			await updateRecipeFermentationSteps(recipe.id, fermentationSteps);
			fermSaveStatus = 'success';
		} catch (e) {
			console.error('Failed to save fermentation steps', e);
			fermSaveStatus = 'error';
		} finally {
			fermSaving = false;
		}
	}

	async function saveWaterProfiles() {
		if (!recipe) return;
		waterProfileSaving = true;
		waterProfileSaveStatus = null;
		try {
			await updateRecipeWaterProfiles(recipe.id, waterProfiles);
			waterProfileSaveStatus = 'success';
		} catch (e) {
			console.error('Failed to save water profiles', e);
			waterProfileSaveStatus = 'error';
		} finally {
			waterProfileSaving = false;
		}
	}

	async function saveWaterAdjustments() {
		if (!recipe) return;
		waterAdjSaving = true;
		waterAdjSaveStatus = null;
		try {
			await updateRecipeWaterAdjustments(recipe.id, waterAdjustments);
			waterAdjSaveStatus = 'success';
		} catch (e) {
			console.error('Failed to save water adjustments', e);
			waterAdjSaveStatus = 'error';
		} finally {
			waterAdjSaving = false;
		}
	}

	async function saveMiscs() {
		if (!recipe) return;
		miscSaving = true;
		miscSaveStatus = null;
		try {
			await updateRecipeMiscs(recipe.id, miscs);
			miscSaveStatus = 'success';
		} catch (e) {
			console.error('Failed to save miscs', e);
			miscSaveStatus = 'error';
		} finally {
			miscSaving = false;
		}
	}

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
				// Pass null through — backend treats explicit null as "clear FK".
				// Collapsing to undefined would drop the clear path entirely.
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
						amount_ml: h.is_extract ? h.amount_ml ?? null : null,
						// Imported hop stand temperature derates whirlpool IBU
						// (tilt_ui-2mxj); dropping it here would re-inflate it.
						whirlpool_temp_c: h.whirlpool_temp_c ?? null
					}))
				}
			};

			// Stats sent in recipeUpdate (og/fg/abv/ibu/color_srm) come from the
			// form, which carries either the user's typed values or imported
			// targets. Don't auto-recalculate — that would silently overwrite
			// both. A separate "Recalculate from ingredients" action calls
			// POST /recipes/{id}/recalculate when the user wants that.
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

		<!-- Nested Collections Editors -->
		<div class="nested-editors">
			<details class="editor-accordion">
				<summary>Mash Schedule ({mashSteps.length} steps)</summary>
				<div class="editor-content">
					<MashScheduleEditor steps={mashSteps} onUpdate={(s) => (mashSteps = s)} />
					<div class="save-row">
						<button class="btn-collection-save" onclick={saveMashSteps} disabled={mashSaving}>
							{mashSaving ? 'Saving...' : 'Save Mash Schedule'}
						</button>
						{#if mashSaveStatus === 'success'}
							<span class="save-success">Saved!</span>
						{:else if mashSaveStatus === 'error'}
							<span class="save-error">Failed to save</span>
						{/if}
					</div>
				</div>
			</details>

			<details class="editor-accordion">
				<summary>Fermentation Schedule ({fermentationSteps.length} steps)</summary>
				<div class="editor-content">
					<FermentationScheduleEditor
						steps={fermentationSteps}
						onUpdate={(s) => (fermentationSteps = s)}
					/>
					<div class="save-row">
						<button class="btn-collection-save" onclick={saveFermentationSteps} disabled={fermSaving}>
							{fermSaving ? 'Saving...' : 'Save Fermentation Schedule'}
						</button>
						{#if fermSaveStatus === 'success'}
							<span class="save-success">Saved!</span>
						{:else if fermSaveStatus === 'error'}
							<span class="save-error">Failed to save</span>
						{/if}
					</div>
				</div>
			</details>

			<details class="editor-accordion">
				<summary>Water Profiles ({waterProfiles.length} profiles)</summary>
				<div class="editor-content">
					<WaterProfileEditor profiles={waterProfiles} onUpdate={(p) => (waterProfiles = p)} />
					<div class="save-row">
						<button
							class="btn-collection-save"
							onclick={saveWaterProfiles}
							disabled={waterProfileSaving}
						>
							{waterProfileSaving ? 'Saving...' : 'Save Water Profiles'}
						</button>
						{#if waterProfileSaveStatus === 'success'}
							<span class="save-success">Saved!</span>
						{:else if waterProfileSaveStatus === 'error'}
							<span class="save-error">Failed to save</span>
						{/if}
					</div>
				</div>
			</details>

			<details class="editor-accordion">
				<summary>Water Adjustments ({waterAdjustments.length} stages)</summary>
				<div class="editor-content">
					<WaterAdjustmentEditor
						adjustments={waterAdjustments}
						onUpdate={(a) => (waterAdjustments = a)}
					/>
					<div class="save-row">
						<button class="btn-collection-save" onclick={saveWaterAdjustments} disabled={waterAdjSaving}>
							{waterAdjSaving ? 'Saving...' : 'Save Water Adjustments'}
						</button>
						{#if waterAdjSaveStatus === 'success'}
							<span class="save-success">Saved!</span>
						{:else if waterAdjSaveStatus === 'error'}
							<span class="save-error">Failed to save</span>
						{/if}
					</div>
				</div>
			</details>

			<details class="editor-accordion">
				<summary>Miscellaneous Ingredients ({miscs.length} items)</summary>
				<div class="editor-content">
					<MiscEditor items={miscs} onUpdate={(m) => (miscs = m)} />
					<div class="save-row">
						<button class="btn-collection-save" onclick={saveMiscs} disabled={miscSaving}>
							{miscSaving ? 'Saving...' : 'Save Misc Ingredients'}
						</button>
						{#if miscSaveStatus === 'success'}
							<span class="save-success">Saved!</span>
						{:else if miscSaveStatus === 'error'}
							<span class="save-error">Failed to save</span>
						{/if}
					</div>
				</div>
			</details>
		</div>
	{/if}
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

	.error-message,
	.error-text {
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

	.spinner,
	.spinner-large {
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
		.spinner-large,
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

	.loading-state,
	.error-state {
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

	.loading-state p,
	.error-state p {
		margin: 0;
	}

	.error-state .error-message {
		flex: none;
		color: var(--status-danger);
	}

	/* Nested collection editors: hairline accordions, no cards */
	.nested-editors {
		display: flex;
		flex-direction: column;
		margin-top: var(--space-xl);
		border-top: 1px solid var(--rule-hairline);
	}

	.editor-accordion {
		border-bottom: 1px solid var(--rule-hairline);
	}

	.editor-accordion summary {
		display: flex;
		align-items: center;
		min-height: 44px;
		padding: var(--space-xs) 0;
		cursor: pointer;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		letter-spacing: 0.04em;
		color: var(--ink-primary);
		list-style: none;
	}

	.editor-accordion summary::-webkit-details-marker {
		display: none;
	}

	.editor-accordion summary::before {
		content: '+';
		display: inline-block;
		width: 20px;
		font-family: var(--font-num);
		font-weight: 500;
		color: var(--ink-muted);
	}

	.editor-accordion[open] summary::before {
		content: '\2212';
	}

	.editor-accordion summary:hover {
		color: var(--accent);
	}

	.editor-accordion summary:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.editor-content {
		padding: var(--space-sm) 0 var(--space-lg);
	}

	.btn-collection-save {
		min-height: 44px;
		padding: var(--space-xs) var(--space-md);
		background: transparent;
		color: var(--ink-primary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
		transition: border-color var(--transition), color var(--transition);
	}

	.btn-collection-save:hover:not(:disabled) {
		border-color: var(--accent);
		color: var(--accent);
	}

	.btn-collection-save:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.btn-collection-save:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.save-row {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-top: var(--space-md);
		flex-wrap: wrap;
	}

	.save-success {
		color: var(--status-steady);
		font-size: var(--text-sm);
		font-weight: 600;
	}

	.save-error {
		color: var(--status-danger);
		font-size: var(--text-sm);
		font-weight: 600;
		padding: 2px var(--space-xs);
		border: 1px solid var(--status-danger);
		border-radius: 4px;
	}
</style>
