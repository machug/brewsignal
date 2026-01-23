<script lang="ts" module>
	import type { FermentableResponse, HopVarietyResponse, YeastStrainResponse, RecipeResponse } from '$lib/api';

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
	import { marked } from 'marked';
	import { fetchYeastStrains, reviewRecipe, searchStyles, type RecipeReviewResponse, type BJCPStyleResponse } from '$lib/api';
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
		initialData?: RecipeResponse;
		onSave?: (recipe: RecipeData) => void;
		onCancel?: () => void;
	}

	let { initialData, onSave, onCancel }: Props = $props();

	// Expose methods and state for parent to render actions
	export function save() {
		handleSave();
	}

	export function review() {
		handleReview();
	}

	export function getReviewLoading() {
		return reviewLoading;
	}

	export function canSave() {
		return name.trim().length > 0;
	}

	// Recipe metadata
	let name = $state('');
	let author = $state('');
	let styleInput = $state('');
	let notes = $state('');

	// Style search/autocomplete state
	let styleResults = $state<BJCPStyleResponse[]>([]);
	let selectedStyle = $state<BJCPStyleResponse | null>(null);
	let styleSearchLoading = $state(false);
	let showStyleDropdown = $state(false);
	let styleSearchTimeout: ReturnType<typeof setTimeout> | null = null;
	let styleBlurTimeout: ReturnType<typeof setTimeout> | null = null;

	// Batch parameters
	let batchSizeLiters = $state(20);
	let efficiencyPercent = $state(72);
	let boilTimeMinutes = $state(60);

	// Ingredients
	let fermentables = $state<RecipeFermentable[]>([]);
	let hops = $state<RecipeHop[]>([]);
	let selectedYeast = $state<YeastStrainResponse | null>(null);
	let showYeastModal = $state(false);

	// AI Review state
	let showReviewModal = $state(false);
	let reviewResult = $state<RecipeReviewResponse | null>(null);
	let reviewLoading = $state(false);
	let reviewError = $state<string | null>(null);

	// Validation error state
	let validationError = $state<string | null>(null);

	// Initialize from existing recipe data (edit mode)
	$effect(() => {
		if (initialData) {
			name = initialData.name || '';
			author = initialData.author || '';
			styleInput = initialData.type || '';
			notes = initialData.notes || '';
			batchSizeLiters = initialData.batch_size_liters || 20;
			efficiencyPercent = initialData.efficiency_percent || 72;
			boilTimeMinutes = initialData.boil_time_minutes || 60;

			// Load fermentables - prefer format_extensions, fall back to API response
			const ext = initialData.format_extensions as { fermentables?: RecipeFermentable[]; hops?: RecipeHop[] } | undefined;
			if (ext?.fermentables && ext.fermentables.length > 0) {
				fermentables = ext.fermentables;
			} else if (initialData.fermentables && initialData.fermentables.length > 0) {
				// Map from API response format to RecipeFermentable format
				fermentables = initialData.fermentables.map((f) => ({
					id: f.id,
					name: f.name,
					type: f.type,
					amount_kg: f.amount_kg || 0,
					potential_sg: f.yield_percent ? 1 + (f.yield_percent / 100) * 0.046 : undefined, // Convert yield% to potential SG
					color_srm: f.color_srm,
					origin: f.origin,
					maltster: f.supplier,
					source: 'recipe',
					is_custom: false,
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString()
				})) as RecipeFermentable[];
			}

			// Load hops - prefer format_extensions, fall back to API response
			if (ext?.hops && ext.hops.length > 0) {
				hops = ext.hops;
			} else if (initialData.hops && initialData.hops.length > 0) {
				// Map from API response format to RecipeHop format
				// BeerJSON uses 'duration', some sources use 'time' - check both
				hops = initialData.hops.map((h) => {
					const timing = h.timing || {};
					const timeValue = timing.duration?.value ?? timing.time?.value ?? 0;
					const timeUnit = timing.duration?.unit ?? timing.time?.unit ?? 'min';
					// Convert to minutes for boil_time_minutes
					const boilMinutes = timeUnit === 'day' ? timeValue * 24 * 60 : timeValue;

					return {
						id: h.id,
						name: h.name,
						origin: h.origin,
						amount_grams: h.amount_grams || 0,
						alpha_acid_percent: h.alpha_acid_percent || 0,
						boil_time_minutes: boilMinutes,
						use: (timing.use?.replace(' ', '_') || 'boil') as HopUse,
						form: (h.form || 'pellet') as HopForm,
						source: 'recipe',
						is_custom: false,
						created_at: new Date().toISOString(),
						updated_at: new Date().toISOString()
					};
				}) as RecipeHop[];
			}

			// Load yeast info (construct a YeastStrainResponse from recipe data)
			if (initialData.yeast_name) {
				selectedYeast = {
					id: 0,
					name: initialData.yeast_name,
					producer: initialData.yeast_lab || undefined,
					product_id: initialData.yeast_product_id || undefined,
					temp_low: initialData.yeast_temp_min || undefined,
					temp_high: initialData.yeast_temp_max || undefined,
					attenuation_low: initialData.yeast_attenuation ? initialData.yeast_attenuation - 2 : undefined,
					attenuation_high: initialData.yeast_attenuation ? initialData.yeast_attenuation + 2 : undefined,
					source: 'recipe',
					is_custom: false,
					created_at: new Date().toISOString(),
					updated_at: new Date().toISOString()
				};
			}
		}
	});

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

	// Style warnings (proactive validation against BJCP guidelines)
	interface StyleWarning {
		stat: string;
		value: string;
		range: string;
		severity: 'warning' | 'error';
	}

	let styleWarnings = $derived(() => {
		if (!selectedStyle) return [];

		const stats = recipeStats();
		const warnings: StyleWarning[] = [];
		const style = selectedStyle;

		// Check OG
		if (style.og_min !== undefined && style.og_max !== undefined) {
			if (stats.og < style.og_min) {
				warnings.push({
					stat: 'OG',
					value: stats.og.toFixed(3),
					range: `${style.og_min.toFixed(3)} - ${style.og_max.toFixed(3)}`,
					severity: 'warning'
				});
			} else if (stats.og > style.og_max) {
				warnings.push({
					stat: 'OG',
					value: stats.og.toFixed(3),
					range: `${style.og_min.toFixed(3)} - ${style.og_max.toFixed(3)}`,
					severity: 'warning'
				});
			}
		}

		// Check FG
		if (style.fg_min !== undefined && style.fg_max !== undefined) {
			if (stats.fg < style.fg_min || stats.fg > style.fg_max) {
				warnings.push({
					stat: 'FG',
					value: stats.fg.toFixed(3),
					range: `${style.fg_min.toFixed(3)} - ${style.fg_max.toFixed(3)}`,
					severity: 'warning'
				});
			}
		}

		// Check ABV
		if (style.abv_min !== undefined && style.abv_max !== undefined) {
			if (stats.abv < style.abv_min || stats.abv > style.abv_max) {
				warnings.push({
					stat: 'ABV',
					value: `${stats.abv.toFixed(1)}%`,
					range: `${style.abv_min.toFixed(1)}% - ${style.abv_max.toFixed(1)}%`,
					severity: 'warning'
				});
			}
		}

		// Check IBU
		if (style.ibu_min !== undefined && style.ibu_max !== undefined) {
			if (stats.ibu < style.ibu_min || stats.ibu > style.ibu_max) {
				warnings.push({
					stat: 'IBU',
					value: stats.ibu.toFixed(0),
					range: `${style.ibu_min} - ${style.ibu_max}`,
					severity: 'warning'
				});
			}
		}

		// Check Color (SRM)
		if (style.srm_min !== undefined && style.srm_max !== undefined) {
			if (stats.srm < style.srm_min || stats.srm > style.srm_max) {
				warnings.push({
					stat: 'Color',
					value: `${stats.srm.toFixed(0)} SRM`,
					range: `${style.srm_min} - ${style.srm_max} SRM`,
					severity: 'warning'
				});
			}
		}

		return warnings;
	});

	// Style search with debounce
	async function handleStyleSearch(query: string) {
		// Cancel any pending blur when user is actively typing
		if (styleBlurTimeout) {
			clearTimeout(styleBlurTimeout);
			styleBlurTimeout = null;
		}

		if (query.length < 2) {
			styleResults = [];
			showStyleDropdown = false;
			return;
		}

		if (styleSearchTimeout) {
			clearTimeout(styleSearchTimeout);
		}

		styleSearchTimeout = setTimeout(async () => {
			styleSearchLoading = true;
			try {
				styleResults = await searchStyles(query, 8);
				showStyleDropdown = styleResults.length > 0;
			} catch (err) {
				console.error('Failed to search styles:', err);
				styleResults = [];
			} finally {
				styleSearchLoading = false;
			}
		}, 300);
	}

	function handleStyleInputChange(event: Event) {
		const input = event.target as HTMLInputElement;
		styleInput = input.value;
		// Clear selected style when user types (they might be searching for a new one)
		if (selectedStyle && styleInput !== selectedStyle.name) {
			selectedStyle = null;
		}
		handleStyleSearch(styleInput);
	}

	function selectStyle(style: BJCPStyleResponse) {
		// Cancel blur timeout since we're making a selection
		if (styleBlurTimeout) {
			clearTimeout(styleBlurTimeout);
			styleBlurTimeout = null;
		}
		selectedStyle = style;
		styleInput = style.name;
		showStyleDropdown = false;
		styleResults = [];
	}

	function clearStyle() {
		selectedStyle = null;
		styleInput = '';
		styleResults = [];
		showStyleDropdown = false;
	}

	function handleStyleFocus() {
		// Cancel any pending blur
		if (styleBlurTimeout) {
			clearTimeout(styleBlurTimeout);
			styleBlurTimeout = null;
		}
		if (styleInput.length >= 2 && styleResults.length > 0) {
			showStyleDropdown = true;
		}
	}

	function handleStyleBlur() {
		// Use a timeout to allow click events on dropdown items to fire first
		styleBlurTimeout = setTimeout(() => {
			showStyleDropdown = false;
			styleBlurTimeout = null;
		}, 150);
	}

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
			validationError = 'Please enter a recipe name';
			return;
		}
		validationError = null;

		const recipe: RecipeData = {
			name,
			author,
			type: styleInput,
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
		if (!styleInput.trim()) {
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
				style: styleInput,
				og: stats.og,
				fg: stats.fg,
				abv: stats.abv,
				ibu: stats.ibu,
				color_srm: stats.srm,
				fermentables: fermentables.map((f) => ({
					name: f.name,
					amount_kg: f.amount_kg,
					color_srm: f.color_srm,
					type: f.type
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
							attenuation: selectedYeast.attenuation_low && selectedYeast.attenuation_high
								? (selectedYeast.attenuation_low + selectedYeast.attenuation_high) / 2
								: undefined
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
	{#if validationError}
		<div class="validation-error">
			<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			<span class="error-text">{validationError}</span>
			<button class="error-dismiss" onclick={() => (validationError = null)} aria-label="Dismiss">
				<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>
	{/if}

	<!-- Stats Panel (always visible) -->
	{#if true}
		{@const stats = recipeStats()}
	<div class="stats-panel">
		<div class="beer-hero">
			<div class="beer-preview" aria-hidden="true">
				<div class="beer-glow" style="--beer-color: {stats.color_hex}"></div>
				<div class="beer-glass" style="--beer-color: {stats.color_hex}">
					<div class="beer-foam">
						<div class="foam-bubble"></div>
						<div class="foam-bubble"></div>
						<div class="foam-bubble"></div>
					</div>
					<div class="beer-liquid">
						<div class="carbonation">
							<span class="bubble"></span>
							<span class="bubble"></span>
							<span class="bubble"></span>
							<span class="bubble"></span>
							<span class="bubble"></span>
						</div>
					</div>
					<div class="beer-gloss"></div>
					<div class="condensation"></div>
				</div>
			</div>
			<div class="beer-meta">
				<span class="stat-label">Color</span>
				{#key stats.srm}
					<span class="stat-value stat-animate">{stats.srm.toFixed(0)} SRM</span>
				{/key}
				<span class="stat-sub">{srmToDescription(stats.srm)}</span>
			</div>
		</div>

		<div class="stats-grid">
			<div class="stat-group">
				<div class="stat">
					<span class="stat-label">OG</span>
					{#key stats.og}
						<span class="stat-value stat-animate">{stats.og.toFixed(3)}</span>
					{/key}
				</div>
				<div class="stat">
					<span class="stat-label">FG</span>
					{#key stats.fg}
						<span class="stat-value stat-animate">{stats.fg.toFixed(3)}</span>
					{/key}
				</div>
				<div class="stat">
					<span class="stat-label">ABV</span>
					{#key stats.abv}
						<span class="stat-value stat-animate">{stats.abv.toFixed(1)}%</span>
					{/key}
				</div>
			</div>

			<div class="stat-group">
				<div class="stat">
					<span class="stat-label">IBU</span>
					{#key stats.ibu}
						<span class="stat-value stat-animate">{stats.ibu.toFixed(0)}</span>
					{/key}
				</div>
				<div class="stat">
					<span class="stat-label">BU:GU</span>
					{#key buguRatio()}
						<span class="stat-value stat-animate balance">{buguRatio().toFixed(2)}</span>
					{/key}
					<span class="stat-sub">{balanceDescription()}</span>
				</div>
			</div>

			<div class="stat-group">
				<div class="stat">
					<span class="stat-label">Calories</span>
					{#key stats.calories_per_330ml}
						<span class="stat-value stat-animate">{stats.calories_per_330ml}</span>
					{/key}
					<span class="stat-sub">per 330ml</span>
				</div>
			</div>
		</div>
	</div>
	{/if}

	<!-- Style Warnings (proactive BJCP validation) -->
	{#if styleWarnings().length > 0}
		<div class="style-warnings">
			<svg class="warnings-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
			</svg>
			<span class="warnings-label">Style Guidelines</span>
			<div class="warnings-list">
				{#each styleWarnings() as warning}
					<span class="warning-badge {warning.severity}">
						{#if warning.severity === 'error'}
							<svg class="badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
								<circle cx="12" cy="12" r="10" />
								<path stroke-linecap="round" d="M15 9l-6 6M9 9l6 6" />
							</svg>
						{:else}
							<svg class="badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
								<circle cx="12" cy="12" r="10" />
								<path stroke-linecap="round" d="M12 8v4M12 16h.01" />
							</svg>
						{/if}
						<span class="badge-stat">{warning.stat}</span>
						<span class="badge-value">{warning.value}</span>
						<span class="badge-target">→ {warning.range}</span>
					</span>
				{/each}
			</div>
		</div>
	{/if}

	<!-- Recipe Metadata -->
	<div class="section section-card metadata-section">
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
			<div class="form-field style-autocomplete">
				<label for="style">Style</label>
				<div class="autocomplete-container">
					<input
						id="style"
						type="text"
						value={styleInput}
						oninput={handleStyleInputChange}
						onfocus={handleStyleFocus}
						onblur={handleStyleBlur}
						placeholder="Search BJCP styles..."
						class="form-input"
						autocomplete="off"
					/>
					{#if styleSearchLoading}
						<span class="autocomplete-spinner"></span>
					{/if}
					{#if selectedStyle}
						<button type="button" class="clear-style" onclick={clearStyle} aria-label="Clear style">&times;</button>
					{/if}
				</div>
				{#if showStyleDropdown && styleResults.length > 0}
					<ul class="style-dropdown">
						{#each styleResults as style}
							<li>
								<button type="button" class="style-option" onclick={() => selectStyle(style)}>
									<span class="style-name">{style.name}</span>
									{#if style.category}
										<span class="style-category">{style.category}</span>
									{/if}
								</button>
							</li>
						{/each}
					</ul>
				{/if}
			</div>
		</div>
	</div>

	<!-- Batch Parameters -->
	<div class="section section-card params-section">
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
	<div class="section ingredient-section">
		<FermentableSelector
			{fermentables}
			{batchSizeLiters}
			{efficiencyPercent}
			onUpdate={handleFermentablesUpdate}
		/>
	</div>

	<!-- Hops -->
	<div class="section ingredient-section">
		<HopSelector hops={hops} og={recipeStats().og} {batchSizeLiters} onUpdate={handleHopsUpdate} />
	</div>

	<!-- Yeast -->
	<div class="section ingredient-section yeast-selector">
		<div class="selector-header yeast-header">
			<div class="header-left">
				<h3>
					<span class="header-icon">
						<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
							<circle cx="12" cy="8" r="4" />
							<circle cx="8" cy="16" r="3" />
							<circle cx="16" cy="17" r="2.5" />
						</svg>
					</span>
					Yeast
				</h3>
				{#if selectedYeast}
					<span class="stats">
						{#if selectedYeast.attenuation_low || selectedYeast.attenuation_high}
							<span class="stat">{selectedYeast.attenuation_low ?? '?'}-{selectedYeast.attenuation_high ?? '?'}% atten</span>
						{/if}
						{#if selectedYeast.temp_low || selectedYeast.temp_high}
							<span class="stat">{selectedYeast.temp_low ?? '?'}-{selectedYeast.temp_high ?? '?'}°C</span>
						{/if}
					</span>
				{/if}
			</div>
			<button type="button" class="add-btn" onclick={() => (showYeastModal = true)}>
				{selectedYeast ? 'Change' : '+ Add Yeast'}
			</button>
		</div>

		{#if !selectedYeast}
			<div class="empty-state yeast-empty">
				<p>No yeast selected yet.</p>
			</div>
		{:else}
			<div class="yeast-item">
				<div class="yeast-main">
					<div class="yeast-info">
						<span class="yeast-name">{selectedYeast.name}</span>
						{#if selectedYeast.type}
							<span class="yeast-type">{selectedYeast.type}</span>
						{/if}
					</div>
					<div class="yeast-details">
						{#if selectedYeast.producer}
							<span class="detail">{selectedYeast.producer}</span>
						{/if}
						{#if selectedYeast.product_id}
							<span class="detail">{selectedYeast.product_id}</span>
						{/if}
						{#if selectedYeast.flocculation}
							<span class="detail">Floc: {selectedYeast.flocculation}</span>
						{/if}
					</div>
				</div>
				<button type="button" class="remove-btn" onclick={() => handleYeastSelect(null)} aria-label="Remove yeast">
					×
				</button>
			</div>
		{/if}
	</div>

	<!-- Notes -->
	<div class="section section-card notes-section">
		<h2 class="section-title">Notes</h2>
		<textarea
			bind:value={notes}
			placeholder="Brewing notes, tips, or variations..."
			rows="4"
			class="notes-input"
		></textarea>
	</div>

</div>

<!-- Yeast Selection Modal -->
{#if showYeastModal}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="modal-overlay" onclick={() => (showYeastModal = false)} onkeydown={(e) => e.key === 'Escape' && (showYeastModal = false)} role="presentation">
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="yeast-modal-title" tabindex="-1" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()}>
			<div class="modal-header">
				<h2 id="yeast-modal-title">Select Yeast</h2>
				<button class="modal-close" onclick={() => (showYeastModal = false)} aria-label="Close">&times;</button>
			</div>
			<div class="modal-body">
				<YeastSelector
					selectedYeastId={selectedYeast?.id}
					onSelect={(yeast) => {
						handleYeastSelect(yeast);
						if (yeast) showYeastModal = false;
					}}
					label=""
				/>
			</div>
		</div>
	</div>
{/if}

<!-- AI Review Modal -->
{#if showReviewModal}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div class="modal-overlay" onclick={closeReviewModal} onkeydown={(e) => e.key === 'Escape' && closeReviewModal()} role="presentation">
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal-content" role="dialog" aria-modal="true" aria-labelledby="review-modal-title" tabindex="-1" onkeydown={(e) => e.stopPropagation()}>
			<div class="modal-header">
				<h2 id="review-modal-title">AI Recipe Review</h2>
				<button class="modal-close" onclick={closeReviewModal} aria-label="Close">&times;</button>
			</div>
			<div class="modal-body">
				{#if reviewLoading}
					<div class="review-loading">
						<div class="spinner"></div>
						<p>Analyzing your recipe against {styleInput || 'style guidelines'}...</p>
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
					<div class="review-content markdown-body">
						{@html marked(reviewResult.review)}
					</div>
				{/if}
			</div>
		</div>
	</div>
{/if}

<style>
	.recipe-builder {
		--accent-primary: var(--recipe-accent);
		--accent-secondary: var(--recipe-accent-hover);
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
		max-width: 900px;
		margin: 0 auto;
	}

	/* Validation Error Banner */
	.validation-error {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		background: var(--error-bg);
		border: 1px solid var(--negative);
		border-radius: 6px;
		color: var(--negative);
		font-size: 14px;
	}

	.validation-error .error-icon {
		width: 18px;
		height: 18px;
		flex-shrink: 0;
	}

	.validation-error .error-text {
		flex: 1;
	}

	.validation-error .error-dismiss {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 22px;
		height: 22px;
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

	.validation-error .error-dismiss:hover {
		opacity: 1;
		background: var(--negative-muted);
	}

	.validation-error .error-dismiss svg {
		width: 14px;
		height: 14px;
	}

	/* Stats Panel */
	.stats-panel {
		position: sticky;
		top: 0;
		z-index: 100;
		display: grid;
		grid-template-columns: minmax(180px, 240px) 1fr;
		align-items: center;
		gap: var(--space-5);
		padding: var(--space-5);
		background: var(--bg-elevated);
		background-image:
			linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(24, 24, 27, 0) 65%),
			var(--recipe-grain-texture);
		background-size: cover, 8px 8px;
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4);
		overflow: hidden;
	}

	.stats-grid {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		align-items: center;
	}

	.beer-hero {
		display: flex;
		align-items: center;
		gap: var(--space-5);
	}

	.beer-preview {
		position: relative;
		display: flex;
		align-items: flex-end;
		justify-content: center;
		min-width: 100px;
		padding: 12px;
	}

	.beer-glow {
		position: absolute;
		inset: 0;
		background: radial-gradient(ellipse at center bottom, var(--beer-color), transparent 70%);
		opacity: 0.35;
		filter: blur(20px);
		pointer-events: none;
		transition: opacity 0.4s ease;
	}

	.beer-glass {
		position: relative;
		width: 72px;
		height: 108px;
		border-radius: 14px 14px 10px 10px;
		border: 1.5px solid var(--recipe-glass-border);
		background: linear-gradient(135deg, rgba(255, 255, 255, 0.08) 0%, var(--recipe-glass) 50%, rgba(0, 0, 0, 0.15) 100%);
		box-shadow:
			inset 0 2px 0 rgba(255, 255, 255, 0.25),
			inset 0 -4px 12px rgba(0, 0, 0, 0.3),
			0 16px 32px rgba(0, 0, 0, 0.45),
			0 4px 8px rgba(0, 0, 0, 0.25);
		overflow: hidden;
		transition: transform 0.3s ease, box-shadow 0.3s ease;
	}

	.beer-glass:hover {
		transform: translateY(-2px);
		box-shadow:
			inset 0 2px 0 rgba(255, 255, 255, 0.3),
			inset 0 -4px 12px rgba(0, 0, 0, 0.3),
			0 20px 40px rgba(0, 0, 0, 0.5),
			0 6px 12px rgba(0, 0, 0, 0.3);
	}

	.beer-liquid {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 74%;
		background:
			linear-gradient(180deg, rgba(255, 255, 255, 0.2) 0%, transparent 20%, rgba(0, 0, 0, 0.25) 100%),
			var(--beer-color);
		transition: background 0.5s ease;
	}

	.carbonation {
		position: absolute;
		bottom: 0;
		left: 0;
		right: 0;
		height: 100%;
		pointer-events: none;
	}

	.carbonation .bubble {
		position: absolute;
		bottom: 0;
		width: 3px;
		height: 3px;
		background: rgba(255, 255, 255, 0.5);
		border-radius: 50%;
		animation: rise 3s ease-in infinite;
	}

	.carbonation .bubble:nth-child(1) { left: 20%; animation-delay: 0s; animation-duration: 2.5s; }
	.carbonation .bubble:nth-child(2) { left: 40%; animation-delay: 0.5s; animation-duration: 3s; }
	.carbonation .bubble:nth-child(3) { left: 55%; animation-delay: 1s; animation-duration: 2.8s; }
	.carbonation .bubble:nth-child(4) { left: 70%; animation-delay: 1.5s; animation-duration: 3.2s; }
	.carbonation .bubble:nth-child(5) { left: 30%; animation-delay: 2s; animation-duration: 2.6s; }

	@keyframes rise {
		0% {
			transform: translateY(0) scale(1);
			opacity: 0;
		}
		10% {
			opacity: 0.6;
		}
		90% {
			opacity: 0.3;
		}
		100% {
			transform: translateY(-85px) scale(0.5);
			opacity: 0;
		}
	}

	.beer-foam {
		position: absolute;
		top: 0;
		left: 0;
		right: 0;
		height: 22%;
		background:
			radial-gradient(ellipse at 30% 60%, rgba(255, 255, 255, 0.95) 0%, transparent 60%),
			radial-gradient(ellipse at 70% 40%, rgba(255, 255, 255, 0.9) 0%, transparent 50%),
			var(--recipe-foam);
		box-shadow:
			inset 0 -3px 8px var(--recipe-foam-shadow),
			inset 0 2px 4px rgba(255, 255, 255, 0.4);
		border-bottom: 1px solid rgba(139, 90, 43, 0.3);
	}

	.foam-bubble {
		position: absolute;
		background: rgba(255, 255, 255, 0.7);
		border-radius: 50%;
		box-shadow: inset 0 -1px 2px rgba(0, 0, 0, 0.1);
	}

	.foam-bubble:nth-child(1) { width: 8px; height: 6px; top: 40%; left: 15%; }
	.foam-bubble:nth-child(2) { width: 10px; height: 7px; top: 50%; left: 55%; }
	.foam-bubble:nth-child(3) { width: 6px; height: 5px; top: 35%; left: 75%; }

	.beer-gloss {
		position: absolute;
		top: 10%;
		left: 10%;
		width: 30%;
		height: 75%;
		border-radius: 14px;
		background: linear-gradient(180deg, rgba(255, 255, 255, 0.6) 0%, rgba(255, 255, 255, 0.1) 40%, transparent 100%);
		opacity: 0.65;
		pointer-events: none;
	}

	.condensation {
		position: absolute;
		inset: 0;
		pointer-events: none;
	}

	.condensation::before,
	.condensation::after {
		content: '';
		position: absolute;
		background: rgba(255, 255, 255, 0.5);
		border-radius: 50%;
		box-shadow: 0 1px 1px rgba(0, 0, 0, 0.15);
	}

	.condensation::before {
		width: 4px;
		height: 6px;
		top: 45%;
		right: 12%;
	}

	.condensation::after {
		width: 3px;
		height: 4px;
		top: 62%;
		right: 18%;
	}

	.beer-meta {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.stat-group {
		display: flex;
		gap: var(--space-4);
		padding: 0 var(--space-3);
		border-right: 1px solid rgba(255, 255, 255, 0.06);
	}

	.stat-group:last-child {
		border-right: none;
	}

	.stat {
		display: flex;
		flex-direction: column;
		align-items: center;
		min-width: 60px;
		padding: var(--space-2);
		border-radius: 8px;
		transition: background 0.2s ease;
	}

	.stat:hover {
		background: rgba(255, 255, 255, 0.04);
	}

	.stat-label {
		font-size: 9px;
		font-weight: 700;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.8px;
		margin-bottom: 2px;
	}

	.stat-value {
		font-size: 20px;
		font-weight: 700;
		color: var(--text-primary);
		font-family: var(--font-mono);
		transition: color 0.3s ease, transform 0.3s ease, text-shadow 0.3s ease;
		text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
	}

	.stat-value.balance {
		color: var(--positive);
		text-shadow: 0 0 12px rgba(34, 197, 94, 0.4);
	}

	.stat-animate {
		animation: stat-pop 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
	}

	@keyframes stat-pop {
		0% {
			opacity: 0.4;
			transform: translateY(4px) scale(0.92);
			color: var(--accent);
		}
		50% {
			transform: translateY(-1px) scale(1.04);
		}
		100% {
			opacity: 1;
			transform: translateY(0) scale(1);
			color: var(--text-primary);
		}
	}

	.stat-sub {
		font-size: 10px;
		color: var(--text-tertiary);
		font-weight: 500;
	}

	/* Sections */
	.section {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.section-card {
		position: relative;
		padding: var(--space-5);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.04),
			0 4px 12px rgba(0, 0, 0, 0.15);
		transition: transform 0.2s ease, box-shadow 0.2s ease;
	}

	.section-card:hover {
		transform: translateY(-1px);
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.06),
			0 6px 16px rgba(0, 0, 0, 0.2);
	}

	.section-card::before {
		content: '';
		position: absolute;
		inset: 0;
		background-image: var(--recipe-grain-texture);
		background-size: 8px 8px;
		opacity: 0.35;
		border-radius: inherit;
		pointer-events: none;
	}

	.section-card > * {
		position: relative;
		z-index: 1;
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		font-size: 13px;
		font-weight: 700;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}

	.section-title::before {
		content: '';
		width: 4px;
		height: 16px;
		border-radius: 2px;
		background: currentColor;
		opacity: 0.5;
	}

	.section-title::after {
		content: '';
		flex: 1;
		height: 1px;
		background: linear-gradient(90deg, currentColor, transparent);
		opacity: 0.2;
	}

	/* Metadata Section - Primary importance */
	.metadata-section {
		padding: var(--space-6) var(--space-5);
		border-left: 4px solid rgba(245, 158, 11, 0.6);
		background: linear-gradient(135deg, rgba(245, 158, 11, 0.04) 0%, transparent 50%);
		z-index: 10; /* Ensure style dropdown appears above params section */
	}

	.metadata-section .section-title {
		color: var(--accent);
	}

	/* Params Section - Secondary */
	.params-section {
		padding: var(--space-4) var(--space-5);
		border-left: 3px solid rgba(56, 189, 248, 0.4);
		background: linear-gradient(135deg, rgba(56, 189, 248, 0.03) 0%, transparent 40%);
	}

	.params-section .section-title {
		color: rgb(56, 189, 248);
	}

	/* Notes Section */
	.notes-section {
		padding: var(--space-5);
		border-left: 3px solid rgba(34, 197, 94, 0.4);
		background: linear-gradient(135deg, rgba(34, 197, 94, 0.03) 0%, transparent 40%);
	}

	.notes-section .section-title {
		color: rgb(34, 197, 94);
	}

	/* Ingredient Section - Warm craft feel */
	.ingredient-section {
		position: relative;
		padding: var(--space-5);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 12px;
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.03),
			0 2px 8px rgba(0, 0, 0, 0.12);
		border-left: 3px solid rgba(217, 119, 6, 0.5);
	}

	.ingredient-section::before {
		content: '';
		position: absolute;
		inset: 0;
		background:
			linear-gradient(135deg, rgba(217, 119, 6, 0.04) 0%, transparent 30%),
			var(--recipe-grain-texture);
		background-size: cover, 8px 8px;
		opacity: 0.5;
		border-radius: inherit;
		pointer-events: none;
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

	/* Yeast Selector - Purple Theme */
	.yeast-selector {
		--yeast-accent: rgb(168, 85, 247);
		--yeast-accent-strong: rgba(168, 85, 247, 0.35);
		--yeast-accent-soft: rgba(168, 85, 247, 0.18);
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.yeast-header {
		position: relative;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-4);
		background: var(--bg-elevated);
		background-image: linear-gradient(120deg, var(--yeast-accent-soft), rgba(24, 24, 27, 0) 70%);
		border: 1px solid var(--border-subtle);
		border-radius: 10px;
		overflow: hidden;
	}

	.yeast-header::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 2px;
		background: linear-gradient(90deg, var(--yeast-accent), transparent);
		opacity: 0.7;
	}

	.yeast-header > * {
		position: relative;
		z-index: 1;
	}

	.yeast-selector .header-left {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.yeast-selector h3 {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.yeast-selector .header-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		border-radius: 6px;
		background: var(--yeast-accent-soft);
		color: var(--yeast-accent);
	}

	.yeast-selector .header-icon svg {
		width: 16px;
		height: 16px;
	}

	.yeast-selector .stats {
		font-size: 13px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.yeast-selector .add-btn {
		padding: var(--space-2) var(--space-3);
		background: var(--yeast-accent);
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
		transition: background var(--transition), transform var(--transition), box-shadow var(--transition);
	}

	.yeast-selector .add-btn:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
		box-shadow: 0 10px 16px rgba(0, 0, 0, 0.35);
	}

	.yeast-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-6);
		background: var(--bg-surface);
		border: 1px dashed var(--yeast-accent-strong);
		border-radius: 8px;
	}

	.yeast-empty p {
		color: var(--text-secondary);
		margin: 0;
	}

	/* Yeast Item */
	.yeast-item {
		display: flex;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 8px;
	}

	.yeast-main {
		flex: 1;
		min-width: 0;
	}

	.yeast-info {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		flex-wrap: wrap;
	}

	.yeast-name {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.yeast-type {
		font-size: 11px;
		font-weight: 500;
		text-transform: capitalize;
		padding: 2px 6px;
		border-radius: 4px;
		background: var(--yeast-accent-soft);
		color: rgb(192, 132, 252);
	}

	.yeast-details {
		display: flex;
		gap: var(--space-3);
		margin-top: var(--space-1);
		flex-wrap: wrap;
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

	.review-content :global(p) {
		margin: var(--space-3) 0;
	}

	.review-content :global(p:first-child) {
		margin-top: 0;
	}

	.review-content :global(strong) {
		font-weight: 600;
		color: var(--text-primary);
	}

	.review-content :global(em) {
		font-style: italic;
	}

	.review-content :global(hr) {
		border: none;
		border-top: 1px solid var(--border-subtle);
		margin: var(--space-4) 0;
	}

	/* Style Autocomplete */
	.style-autocomplete {
		position: relative;
	}

	.autocomplete-container {
		position: relative;
		display: flex;
		align-items: center;
	}

	.autocomplete-container .form-input {
		flex: 1;
		padding-right: var(--space-8);
	}

	.autocomplete-spinner {
		position: absolute;
		right: 36px;
		width: 16px;
		height: 16px;
		border: 2px solid var(--border-default);
		border-top-color: var(--accent-primary);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	.clear-style {
		position: absolute;
		right: var(--space-2);
		background: none;
		border: none;
		font-size: 18px;
		color: var(--text-tertiary);
		cursor: pointer;
		padding: var(--space-1);
		line-height: 1;
	}

	.clear-style:hover {
		color: var(--text-primary);
	}

	.style-dropdown {
		position: absolute;
		top: 100%;
		left: 0;
		right: 0;
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		margin-top: var(--space-1);
		max-height: 280px;
		overflow-y: auto;
		z-index: 200;
		box-shadow: 0 8px 16px rgba(0, 0, 0, 0.3);
		list-style: none;
		padding: 0;
	}

	.style-option {
		width: 100%;
		padding: var(--space-3);
		background: none;
		border: none;
		text-align: left;
		cursor: pointer;
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		transition: background var(--transition);
	}

	.style-option:hover {
		background: var(--bg-hover);
	}

	.style-name {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.style-category {
		font-size: 12px;
		color: var(--text-tertiary);
	}

	/* Style Warnings */
	.style-warnings {
		display: flex;
		align-items: flex-start;
		gap: var(--space-3);
		padding: var(--space-4);
		background:
			linear-gradient(135deg, rgba(245, 158, 11, 0.08) 0%, rgba(245, 158, 11, 0.02) 100%);
		border: 1px solid rgba(245, 158, 11, 0.3);
		border-radius: 10px;
		box-shadow: 0 2px 8px rgba(245, 158, 11, 0.1);
	}

	.warnings-icon {
		flex-shrink: 0;
		width: 20px;
		height: 20px;
		color: var(--warning);
	}

	.warnings-label {
		flex-shrink: 0;
		font-size: 11px;
		font-weight: 700;
		color: var(--warning);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		padding-top: 2px;
	}

	.warnings-list {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-2);
		flex: 1;
	}

	.warning-badge {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-3);
		background: var(--bg-elevated);
		border-radius: 6px;
		font-size: 12px;
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.05),
			0 1px 3px rgba(0, 0, 0, 0.2);
		transition: transform 0.15s ease, box-shadow 0.15s ease;
	}

	.warning-badge:hover {
		transform: translateY(-1px);
		box-shadow:
			inset 0 1px 0 rgba(255, 255, 255, 0.08),
			0 3px 6px rgba(0, 0, 0, 0.25);
	}

	.warning-badge .badge-icon {
		width: 14px;
		height: 14px;
		flex-shrink: 0;
	}

	.warning-badge .badge-stat {
		font-weight: 600;
		color: var(--text-secondary);
	}

	.warning-badge .badge-value {
		font-family: var(--font-mono);
		font-weight: 700;
		color: var(--text-primary);
	}

	.warning-badge .badge-target {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-tertiary);
	}

	.warning-badge.warning {
		border-left: 3px solid var(--warning);
	}

	.warning-badge.warning .badge-icon {
		color: var(--warning);
	}

	.warning-badge.error {
		border-left: 3px solid var(--negative);
		background: linear-gradient(135deg, var(--negative-muted) 0%, var(--bg-elevated) 50%);
	}

	.warning-badge.error .badge-icon {
		color: var(--negative);
	}

	/* Top Actions */
	.top-actions {
		border-top: none;
		border-bottom: 1px solid var(--border-subtle);
		padding-top: 0;
		padding-bottom: var(--space-4);
	}

	/* Responsive */
	@media (max-width: 640px) {
		.stats-panel {
			position: relative;
			grid-template-columns: 1fr;
		}

		.beer-hero {
			justify-content: center;
		}

		.beer-preview {
			min-width: 80px;
			padding: 8px;
		}

		.beer-glass {
			width: 56px;
			height: 84px;
		}

		.beer-glow {
			opacity: 0.25;
		}

		.carbonation .bubble {
			width: 2px;
			height: 2px;
		}

		.stats-grid {
			justify-content: space-around;
		}

		.form-grid {
			grid-template-columns: 1fr;
		}

		.form-field.full-width {
			grid-column: 1;
		}
	}
</style>
