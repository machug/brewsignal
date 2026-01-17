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
	import { fetchYeastStrains } from '$lib/api';
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
		<button type="button" class="btn-primary" onclick={handleSave}>Save Recipe</button>
	</div>
</div>

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
