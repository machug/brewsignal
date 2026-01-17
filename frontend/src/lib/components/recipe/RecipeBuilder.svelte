<script lang="ts" module>
	import type { FermentableResponse, HopVarietyResponse, YeastStrainResponse } from '$lib/api';

	export type HopUse = 'boil' | 'whirlpool' | 'dry_hop' | 'first_wort' | 'mash';
	export type HopForm = 'pellet' | 'whole' | 'plug';

	export interface RecipeFermentable extends FermentableResponse {
		amount_kg: number;
	}

	export interface RecipeHop extends HopVarietyResponse {
		amount_grams: number;
		boil_time_minutes: number;
		use: HopUse;
		form: HopForm;
		alpha_acid_percent: number;
	}

	export interface RecipeData {
		name: string;
		author: string;
		type: string;
		batch_size_liters: number;
		efficiency_percent: number;
		boil_time_minutes: number;
		og: number;
		fg: number;
		abv: number;
		ibu: number;
		color_srm: number;
		fermentables: RecipeFermentable[];
		hops: RecipeHop[];
		yeast: YeastStrainResponse | null;
		notes: string;
	}
</script>

<script lang="ts">
	import { onMount } from 'svelte';
	import { fetchYeastStrains, reviewRecipe, type RecipeReviewResponse } from '$lib/api';
	import FermentableSelector from './FermentableSelector.svelte';
	import HopSelector from './HopSelector.svelte';
	import YeastSelector from '$lib/components/batch/YeastSelector.svelte';
	import {
		calculateRecipeStats,
		calculateFG,
		calculateABV,
		srmToHex,
		srmToDescription,
		calculateBUGU,
		type Fermentable,
		type Hop,
		type Yeast,
		type BatchParams
	} from '$lib/brewing';

	interface Props {
		onSave?: (recipe: RecipeData) => void;
		onCancel?: () => void;
	}

	let { onSave, onCancel }: Props = $props();

	// Recipe metadata
	let name = $state('');
	let author = $state('');
	let type = $state('');
	let notes = $state('');

	// Batch parameters
	let batchSizeLiters = $state(20);
	let efficiencyPercent = $state(72);
	let boilTimeMinutes = $state(60);

	// Ingredients
	let fermentables = $state<RecipeFermentable[]>([]);
	let hops = $state<RecipeHop[]>([]);
	let selectedYeast = $state<YeastStrainResponse | null>(null);

	// AI Review state
	let showReviewModal = $state(false);
	let reviewResult = $state<RecipeReviewResponse | null>(null);
	let reviewLoading = $state(false);
	let reviewError = $state<string | null>(null);

	// Calculate recipe stats in real-time
	let recipeStats = $derived(() => {
		if (fermentables.length === 0) {
			return {
				og: 1.0,
				fg: 1.0,
				abv: 0,
				ibu: 0,
				srm: 0,
				color_hex: '#FFE699',
				calories_per_330ml: 0
			};
		}

		// Convert to calculation format
		const calcFermentables: Fermentable[] = fermentables.map((f) => ({
			name: f.name,
			amount_kg: f.amount_kg,
			potential_sg: f.potential_sg || 1.036,
			color_srm: f.color_srm || 2
		}));

		const calcHops: Hop[] = hops.map((h) => ({
			name: h.name,
			amount_grams: h.amount_grams,
			alpha_acid_percent: h.alpha_acid_percent,
			boil_time_minutes: h.boil_time_minutes,
			form: h.form,
			use: h.use
		}));

		// Use default yeast if none selected
		const calcYeast: Yeast = {
			name: selectedYeast?.name || 'Default Yeast',
			attenuation_percent:
				selectedYeast?.attenuation_low && selectedYeast?.attenuation_high
					? (selectedYeast.attenuation_low + selectedYeast.attenuation_high) / 2
					: 75,
			temp_min_c: selectedYeast?.temp_low || 18,
			temp_max_c: selectedYeast?.temp_high || 22
		};

		const batch: BatchParams = {
			batch_size_liters: batchSizeLiters,
			efficiency_percent: efficiencyPercent,
			boil_time_minutes: boilTimeMinutes
		};

		return calculateRecipeStats(calcFermentables, calcHops, calcYeast, batch);
	});

	// BU:GU ratio
	let buguRatio = $derived(() => calculateBUGU(recipeStats().ibu, recipeStats().og));

	// Balance description
	let balanceDescription = $derived(() => {
		const ratio = buguRatio();
		if (ratio < 0.3) return 'Very Malty';
		if (ratio < 0.5) return 'Malty';
		if (ratio < 0.7) return 'Balanced';
		if (ratio < 0.9) return 'Hoppy';
		return 'Very Bitter';
	});

	function handleFermentablesUpdate(updated: RecipeFermentable[]) {
		fermentables = updated;
	}

	function handleHopsUpdate(updated: RecipeHop[]) {
		hops = updated;
	}

	function handleYeastSelect(yeast: YeastStrainResponse | null) {
		selectedYeast = yeast;
	}

	function handleSave() {
		if (!name.trim()) {
			alert('Please enter a recipe name');
			return;
		}

		const recipe: RecipeData = {
			name,
			author,
			type,
			batch_size_liters: batchSizeLiters,
			efficiency_percent: efficiencyPercent,
			boil_time_minutes: boilTimeMinutes,
			og: recipeStats().og,
			fg: recipeStats().fg,
			abv: recipeStats().abv,
			ibu: recipeStats().ibu,
			color_srm: recipeStats().srm,
			fermentables,
			hops,
			yeast: selectedYeast,
			notes
		};

		onSave?.(recipe);
	}

	async function handleReview() {
		if (!type.trim()) {
			reviewError = 'Please enter a beer style to get an AI review';
			showReviewModal = true;
			return;
		}

		if (fermentables.length === 0) {
			reviewError = 'Please add at least one fermentable to get an AI review';
			showReviewModal = true;
			return;
		}

		reviewLoading = true;
		reviewError = null;
		showReviewModal = true;

		try {
			const stats = recipeStats();
			reviewResult = await reviewRecipe({
				name: name || 'Untitled Recipe',
				style: type,
				og: stats.og,
				fg: stats.fg,
				abv: stats.abv,
				ibu: stats.ibu,
				color_srm: stats.srm,
				fermentables: fermentables.map((f) => ({
					name: f.name,
					amount_kg: f.amount_kg,
					color_srm: f.color_srm,
					type: f.category
				})),
				hops: hops.map((h) => ({
					name: h.name,
					amount_grams: h.amount_grams,
					boil_time_minutes: h.boil_time_minutes,
					alpha_acid_percent: h.alpha_acid_percent,
					use: h.use
				})),
				yeast: selectedYeast
					? {
							name: selectedYeast.name,
							producer: selectedYeast.producer,
							attenuation: selectedYeast.attenuation
						}
					: undefined
			});
		} catch (err) {
			reviewError = err instanceof Error ? err.message : 'Failed to get AI review';
		} finally {
			reviewLoading = false;
		}
	}

	function closeReviewModal() {
		showReviewModal = false;
		reviewResult = null;
		reviewError = null;
	}
</script>

<div class="recipe-builder">
	<!-- Stats Panel (always visible) -->
	<div class="stats-panel">
		<div class="stat-group">
			<div class="stat">
				<span class="stat-label">OG</span>
				<span class="stat-value">{recipeStats().og.toFixed(3)}</span>
			</div>
			<div class="stat">
				<span class="stat-label">FG</span>
				<span class="stat-value">{recipeStats().fg.toFixed(3)}</span>
			</div>
			<div class="stat">
				<span class="stat-label">ABV</span>
				<span class="stat-value">{recipeStats().abv.toFixed(1)}%</span>
			</div>
		</div>

		<div class="stat-group">
			<div class="stat">
				<span class="stat-label">IBU</span>
				<span class="stat-value">{recipeStats().ibu.toFixed(0)}</span>
			</div>
			<div class="stat">
				<span class="stat-label">BU:GU</span>
				<span class="stat-value balance">{buguRatio().toFixed(2)}</span>
				<span class="stat-sub">{balanceDescription()}</span>
			</div>
		</div>

		<div class="stat-group">
			<div class="stat color-stat">
				<span class="stat-label">Color</span>
				<div class="color-display">
					<span class="color-swatch" style="background-color: {recipeStats().color_hex}"></span>
					<span class="stat-value">{recipeStats().srm.toFixed(0)} SRM</span>
				</div>
				<span class="stat-sub">{srmToDescription(recipeStats().srm)}</span>
			</div>
		</div>

		<div class="stat-group">
			<div class="stat">
				<span class="stat-label">Calories</span>
				<span class="stat-value">{recipeStats().calories_per_330ml}</span>
				<span class="stat-sub">per 330ml</span>
			</div>
		</div>
	</div>

	<!-- Recipe Metadata -->
	<div class="section metadata-section">
		<h2 class="section-title">Recipe Details</h2>
		<div class="form-grid">
			<div class="form-field full-width">
				<label for="recipe-name">Recipe Name *</label>
				<input
					id="recipe-name"
					type="text"
					bind:value={name}
					placeholder="e.g., My Awesome IPA"
					class="form-input"
				/>
			</div>
			<div class="form-field">
				<label for="author">Brewer</label>
				<input
					id="author"
					type="text"
					bind:value={author}
					placeholder="Your name"
					class="form-input"
				/>
			</div>
			<div class="form-field">
				<label for="style">Style</label>
				<input
					id="style"
					type="text"
					bind:value={type}
					placeholder="e.g., American IPA"
					class="form-input"
				/>
			</div>
		</div>
	</div>

	<!-- Batch Parameters -->
	<div class="section params-section">
		<h2 class="section-title">Batch Parameters</h2>
		<div class="params-grid">
			<div class="param-field">
				<label for="batch-size">Batch Size</label>
				<div class="input-with-unit">
					<input
						id="batch-size"
						type="number"
						bind:value={batchSizeLiters}
						min="1"
						step="1"
						class="form-input"
					/>
					<span class="unit">L</span>
				</div>
			</div>
			<div class="param-field">
				<label for="efficiency">Efficiency</label>
				<div class="input-with-unit">
					<input
						id="efficiency"
						type="number"
						bind:value={efficiencyPercent}
						min="50"
						max="95"
						step="1"
						class="form-input"
					/>
					<span class="unit">%</span>
				</div>
			</div>
			<div class="param-field">
				<label for="boil-time">Boil Time</label>
				<div class="input-with-unit">
					<input
						id="boil-time"
						type="number"
						bind:value={boilTimeMinutes}
						min="30"
						max="120"
						step="5"
						class="form-input"
					/>
					<span class="unit">min</span>
				</div>
			</div>
		</div>
	</div>

	<!-- Fermentables -->
	<div class="section">
		<FermentableSelector
			{fermentables}
			{batchSizeLiters}
			{efficiencyPercent}
			onUpdate={handleFermentablesUpdate}
		/>
	</div>

	<!-- Hops -->
	<div class="section">
		<HopSelector hops={hops} og={recipeStats().og} {batchSizeLiters} onUpdate={handleHopsUpdate} />
	</div>

	<!-- Yeast -->
	<div class="section yeast-section">
		<YeastSelector
			selectedYeastId={selectedYeast?.id}
			onSelect={handleYeastSelect}
			label="Select Yeast Strain"
		/>
	</div>

	<!-- Notes -->
	<div class="section notes-section">
		<h2 class="section-title">Notes</h2>
		<textarea
			bind:value={notes}
			placeholder="Brewing notes, tips, or variations..."
			rows="4"
			class="notes-input"
		></textarea>
	</div>

	<!-- Actions -->
	<div class="actions">
		{#if onCancel}
			<button type="button" class="btn-secondary" onclick={onCancel}>Cancel</button>
		{/if}
		<button type="button" class="btn-ai" onclick={handleReview} disabled={reviewLoading}>
			{#if reviewLoading}
				Analyzing...
			{:else}
				AI Review
			{/if}
		</button>
		<button type="button" class="btn-primary" onclick={handleSave}>Save Recipe</button>
	</div>
</div>

<!-- AI Review Modal -->
{#if showReviewModal}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<div class="modal-overlay" onclick={closeReviewModal} role="presentation">
		<div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="review-modal-title" tabindex="-1">
			<div class="modal-header">
				<h2 id="review-modal-title">AI Recipe Review</h2>
				<button class="modal-close" onclick={closeReviewModal} aria-label="Close">&times;</button>
			</div>
			<div class="modal-body">
				{#if reviewLoading}
					<div class="review-loading">
						<div class="spinner"></div>
						<p>Analyzing your recipe against {type || 'style guidelines'}...</p>
					</div>
				{:else if reviewError}
					<div class="review-error">
						<p>{reviewError}</p>
					</div>
				{:else if reviewResult}
					<div class="review-meta">
						{#if reviewResult.style_found}
							<span class="style-badge found">BJCP Style: {reviewResult.style_name}</span>
						{:else}
							<span class="style-badge not-found">Style not in BJCP database</span>
						{/if}
						<span class="model-badge">Model: {reviewResult.model}</span>
					</div>
					<div class="review-content">
						{@html reviewResult.review.replace(/\n/g, '<br>')}
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.recipe-builder {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
		max-width: 900px;
		margin: 0 auto;
	}

	/* Stats Panel */
	.stats-panel {
		position: sticky;
		top: 0;
		z-index: 100;
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		padding: var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
	}

	.stat-group {
		display: flex;
		gap: var(--space-4);
	}

	.stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 60px;
	}

	.stat-label {
		font-size: 10px;
		font-weight: 600;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.stat-value {
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
		font-family: var(--font-mono);
	}

	.stat-value.balance {
		color: var(--positive);
	}

	.stat-sub {
		font-size: 10px;
		color: var(--text-tertiary);
	}

	.color-stat {
		min-width: 80px;
	}

	.color-display {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.color-swatch {
		width: 20px;
		height: 20px;
		border-radius: 4px;
		border: 1px solid var(--border-default);
	}

	/* Sections */
	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.section-title {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	/* Metadata Section */
	.metadata-section,
	.params-section,
	.notes-section {
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
	}

	.form-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: var(--space-4);
	}

	.form-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.form-field.full-width {
		grid-column: 1 / -1;
	}

	.form-field label {
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.form-input {
		width: 100%;
		padding: var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
	}

	.form-input:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	/* Params Section */
	.params-grid {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
	}

	.param-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.param-field label {
		font-size: 12px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.input-with-unit {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.input-with-unit .form-input {
		width: 80px;
		text-align: right;
	}

	.unit {
		font-size: 13px;
		color: var(--text-tertiary);
	}

	/* Yeast Section */
	.yeast-section {
		padding: 0;
	}

	/* Notes Section */
	.notes-input {
		width: 100%;
		padding: var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
		font-family: var(--font-sans);
		resize: vertical;
		min-height: 100px;
	}

	.notes-input:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	/* Actions */
	.actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-3);
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

	.btn-secondary:hover {
		background: var(--bg-hover);
	}

	.btn-primary {
		background: var(--accent-primary);
		color: var(--bg-surface);
	}

	.btn-primary:hover {
		background: var(--accent-secondary);
	}

	.btn-ai {
		padding: var(--space-3) var(--space-6);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
		border: 1px solid var(--positive);
		background: transparent;
		color: var(--positive);
	}

	.btn-ai:hover:not(:disabled) {
		background: var(--positive);
		color: var(--bg-surface);
	}

	.btn-ai:disabled {
		opacity: 0.6;
		cursor: wait;
	}

	/* Modal Overlay */
	.modal-overlay {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		bottom: 0;
		background: rgba(0, 0, 0, 0.7);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal-content {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		max-width: 700px;
		width: 100%;
		max-height: 80vh;
		overflow: hidden;
		display: flex;
		flex-direction: column;
		box-shadow: 0 20px 40px rgba(0, 0, 0, 0.4);
	}

	.modal-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: var(--space-4) var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
	}

	.modal-header h2 {
		margin: 0;
		font-size: 18px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.modal-close {
		background: none;
		border: none;
		font-size: 24px;
		color: var(--text-secondary);
		cursor: pointer;
		padding: 0;
		line-height: 1;
	}

	.modal-close:hover {
		color: var(--text-primary);
	}

	.modal-body {
		padding: var(--space-5);
		overflow-y: auto;
	}

	.review-loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-4);
		padding: var(--space-8) 0;
	}

	.spinner {
		width: 40px;
		height: 40px;
		border: 3px solid var(--border-default);
		border-top-color: var(--positive);
		border-radius: 50%;
		animation: spin 1s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.review-loading p {
		color: var(--text-secondary);
		margin: 0;
	}

	.review-error {
		padding: var(--space-4);
		background: var(--negative-bg);
		border: 1px solid var(--negative);
		border-radius: 8px;
		color: var(--negative);
	}

	.review-meta {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		margin-bottom: var(--space-4);
	}

	.style-badge,
	.model-badge {
		display: inline-block;
		padding: var(--space-1) var(--space-3);
		border-radius: 20px;
		font-size: 12px;
		font-weight: 500;
	}

	.style-badge.found {
		background: var(--positive-bg);
		color: var(--positive);
		border: 1px solid var(--positive);
	}

	.style-badge.not-found {
		background: var(--warning-bg);
		color: var(--warning);
		border: 1px solid var(--warning);
	}

	.model-badge {
		background: var(--bg-elevated);
		color: var(--text-secondary);
		border: 1px solid var(--border-default);
	}

	.review-content {
		line-height: 1.7;
		color: var(--text-primary);
	}

	.review-content :global(h3) {
		margin-top: var(--space-5);
		margin-bottom: var(--space-2);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.review-content :global(h3:first-child) {
		margin-top: 0;
	}

	.review-content :global(ul) {
		margin: var(--space-2) 0;
		padding-left: var(--space-5);
	}

	.review-content :global(li) {
		margin-bottom: var(--space-2);
	}

	/* Responsive */
	@media (max-width: 640px) {
		.stats-panel {
			position: relative;
			flex-direction: column;
		}

		.stat-group {
			justify-content: space-around;
			width: 100%;
		}

		.form-grid {
			grid-template-columns: 1fr;
		}

		.form-field.full-width {
			grid-column: 1;
		}
	}
</style>
