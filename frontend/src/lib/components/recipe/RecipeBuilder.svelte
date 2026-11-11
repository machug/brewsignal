<script lang="ts" module>
	import type { FermentableResponse, HopVarietyResponse, YeastStrainResponse, RecipeResponse } from '$lib/api';
	// Shared hop types/constants live in a plain TS module to break the
	// HopSelector ↔ RecipeBuilder ESM cycle (TDZ risk at module init).
	import {
		EXTRACT_USE_ALLOWLIST,
		type ExtractHopUse,
		type HopForm,
		type HopUse,
	} from './hop-types';

	export { EXTRACT_USE_ALLOWLIST };
	export type { ExtractHopUse, HopForm, HopUse };

	/**
	 * Normalize a timing.use value from any source (BeerJSON `add_to_*`,
	 * Brewfather "Dry Hop", or already-short `whirlpool`) into the short
	 * HopUse form used by editor components and the IBU calculator.
	 * Imports persist BeerJSON-style keys (e.g. `add_to_whirlpool`) — without
	 * this normalization, the editor would silently treat them as `boil`.
	 *
	 * When `isExtract` is true the cold-side allowlist values
	 * (`add_to_fermentation`, `add_to_package`, `package`, `keg`, `brite`)
	 * are preserved verbatim so they round-trip through the extract editor
	 * unchanged.
	 */
	export function normalizeHopUse(
		raw: string | undefined,
		isExtract = false,
	): HopUse {
		if (!raw) return isExtract ? 'dry_hop' : 'boil';
		const key = raw.toLowerCase().replace(/ /g, '_');
		if (isExtract) {
			// Preserve long-form cold-side keys for extracts. Anything
			// outside the allowlist falls through to the standard
			// normalizer (so e.g. a stale "boil" on an extract gets
			// remapped to dry_hop below via the default).
			if ((EXTRACT_USE_ALLOWLIST as readonly string[]).includes(key)) {
				return key as HopUse;
			}
			// Already-short dry_hop survives the next lookup; anything
			// else for an extract is coerced to dry_hop, the safest
			// cold-side default.
			if (key === 'dry_hop') return 'dry_hop';
			return 'dry_hop';
		}
		const lookup: Record<string, HopUse> = {
			add_to_boil: 'boil',
			add_to_whirlpool: 'whirlpool',
			add_to_fermentation: 'dry_hop',
			add_to_mash: 'mash',
			boil: 'boil',
			whirlpool: 'whirlpool',
			dry_hop: 'dry_hop',
			first_wort: 'first_wort',
			mash: 'mash',
		};
		return lookup[key] ?? 'boil';
	}

	export interface RecipeFermentable extends FermentableResponse {
		amount_kg: number;
	}

	export interface RecipeHop extends HopVarietyResponse {
		amount_grams: number;
		boil_time_minutes: number;
		use: HopUse;
		form: HopForm;
		alpha_acid_percent: number;
		// Extract mode (Abstrax Quantum-style hop extracts). When
		// is_extract is true the hop is dosed by volume (amount_ml) on
		// the cold side, alpha-acid IBU math is skipped, and `use` is
		// restricted to the cold-side allowlist.
		is_extract?: boolean;
		amount_ml?: number | null;
		// Imported hop stand temperature (Celsius). No editor input yet;
		// carried so saving an imported recipe keeps its whirlpool IBU.
		whirlpool_temp_c?: number | null;
	}

	export interface RecipeData {
		name: string;
		author: string;
		type: string;
		style_id: string | null;
		style: string;
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
	import { fetchYeastStrains, getStyle, reviewRecipe, searchStyles, type RecipeReviewResponse, type BJCPStyleResponse } from '$lib/api';
	import RecipeReviewModal from './RecipeReviewModal.svelte';
	import RecipeStatsPanel from './RecipeStatsPanel.svelte';
	import FermentableSelector from './FermentableSelector.svelte';
	import HopSelector from './HopSelector.svelte';
	import YeastSelector from '$lib/components/batch/YeastSelector.svelte';
	import {
		calculateRecipeStats,
		calculateFG,
		calculateABV,
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
	// Tracks whether the user has edited any inputs that influence the
	// calculated recipe stats (ingredients OR batch params) since the
	// recipe loaded. Used to decide whether AI review should send the
	// brewer-declared target_* stats (clean) or the live calculator
	// output (edited).
	let ingredientsDirty = $state(false);
	let inputsInitialized = $state(false);
	let showYeastModal = $state(false);

	// AI Review state
	let showReviewModal = $state(false);
	let reviewResult = $state<RecipeReviewResponse | null>(null);
	let reviewLoading = $state(false);
	let reviewError = $state<string | null>(null);

	// Validation error state
	let validationError = $state<string | null>(null);

	// Initialize from existing recipe data (edit mode). Always sets
	// inputsInitialized = true at the end so the batch-param watcher
	// below activates even in create mode (where initialData is null).
	$effect(() => {
		if (initialData) {
			name = initialData.name || '';
			author = initialData.author || '';
			// Style picker is bound to BJCP style (style_id FK), not the
			// BeerXML "type" column (ale/lager/all_grain). Initialize from
			// the linked style when present; fall back to the legacy free-text
			// in initialData.type only for recipes saved before the picker
			// produced a style_id, so users still see what they typed.
			if (initialData.style) {
				styleInput = initialData.style.name;
				// RecipeResponse only carries {id, name}; fetch the full BJCP
				// row so style-vs-target warnings (og_min/max etc) populate.
				// Set a stub immediately so the picker shows the chip; replace
				// once the BJCP detail lands. Replace by reference: stub has no
				// og_min/abv_min, so any successful fetch is more complete.
				const styleId = initialData.style.id;
				selectedStyle = { ...initialData.style, guide: '', category_number: '', category: '' } as BJCPStyleResponse;
				getStyle(styleId)
					.then((s) => {
						if (selectedStyle?.id === styleId) selectedStyle = s;
					})
					.catch(() => {});
			} else {
				selectedStyle = null;
				styleInput = initialData.type || '';
			}
			notes = initialData.notes || '';
			batchSizeLiters = initialData.batch_size_liters || 20;
			efficiencyPercent = initialData.efficiency_percent || 72;
			boilTimeMinutes = initialData.boil_time_minutes || 60;

			// Load fermentables - prefer format_extensions, fall back to API response
			const ext = initialData.format_extensions as { fermentables?: RecipeFermentable[]; hops?: RecipeHop[] } | undefined;
			if (ext?.fermentables && ext.fermentables.length > 0) {
				// format_extensions grain rows often omit color_srm, which makes
				// recipeStats() default them to ~2 SRM and report a dark beer as
				// pale (tilt_ui-b94). Backfill color from the colored
				// relationship rows (matched by name, then index) without
				// disturbing the rest of the stored shape.
				const apiFerms = initialData.fermentables ?? [];
				fermentables = ext.fermentables.map((f, i) => {
					// Pick a color, not a row: prefer the same-name row at this
					// index (handles duplicate grain names), then the first
					// name match, then the index row. Keep f.color_srm verbatim
					// when present so a real null isn't turned into undefined.
					const byIndex = apiFerms[i];
					const refColor =
						(byIndex?.name === f.name ? byIndex?.color_srm : undefined) ??
						apiFerms.find((a) => a.name === f.name)?.color_srm ??
						byIndex?.color_srm;
					return { ...f, color_srm: f.color_srm ?? refColor ?? f.color_srm };
				});
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

			// Load hops - prefer format_extensions, fall back to API response.
			// Older saves stored use as the BeerJSON full form
			// ('add_to_boil' / 'add_to_fermentation' / 'add_to_whirlpool')
			// which the editor and IBU calculator don't recognise — normalise
			// to the short HopUse form on load.
			// An explicit empty array in format_extensions is the editor's
			// "user deleted all hops" intent; falling back to recipe.hops
			// would resurrect stale rows. Treat any present array as
			// authoritative — only fall through when the key is absent.
			if (Array.isArray(ext?.hops)) {
				// Preserve the stored boil_time_minutes verbatim — even when
				// it encodes a dry-hop day count as minutes (4 days -> 5760)
				// it's the only persisted copy of that duration. The IBU
				// calc and review payload guard against treating it as a
				// boil time when use is dry_hop / mash.
				hops = ext.hops.map((h: RecipeHop) => ({
					...h,
					use: normalizeHopUse(
						h.use as unknown as string,
						Boolean(h.is_extract),
					),
					is_extract: Boolean(h.is_extract),
					amount_ml: h.is_extract ? h.amount_ml ?? null : null,
				}));
			} else if (initialData.hops && initialData.hops.length > 0) {
				// Map from API response format to RecipeHop format
				// BeerJSON uses 'duration', some sources use 'time' - check both
				hops = initialData.hops.map((h) => {
					const timing = h.timing || {};
					const timeValue = timing.duration?.value ?? timing.time?.value ?? 0;
					const timeUnit = timing.duration?.unit ?? timing.time?.unit ?? 'min';
					const isExtract = Boolean(h.is_extract);
					const normalizedUse = normalizeHopUse(timing.use, isExtract);
					// Convert to minutes for boil_time_minutes. Day units
					// (dry hop) are stored as minutes here so the editor's
					// dual-purpose field round-trips losslessly; the IBU
					// calc and review payload zero this out for dry_hop /
					// mash so it never feeds into utilization math.
					const boilMinutes =
						timeUnit === 'day' ? timeValue * 24 * 60 : timeValue;

					return {
						id: h.id,
						name: h.name,
						origin: h.origin,
						amount_grams: h.amount_grams || 0,
						alpha_acid_percent: h.alpha_acid_percent || 0,
						boil_time_minutes: boilMinutes,
						use: normalizedUse,
						is_extract: isExtract,
						amount_ml: isExtract ? h.amount_ml ?? null : null,
						whirlpool_temp_c: timing.temperature?.value ?? null,
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
		// Mark inputs as initialised AFTER load (or immediately in create
		// mode with no initialData) so the batch-param watcher below
		// doesn't trip on the seed assignments.
		inputsInitialized = true;
	});

	// Watch batch-param edits (these don't go through the handle*Update
	// callbacks because they're bound directly via bind:value). Skip the
	// first run (which fires after the load effect seeds the values) and
	// then flip ingredientsDirty on any subsequent change, so the AI
	// review payload stops trusting target_* once edits begin.
	let batchParamsWatcherFirstRun = true;
	$effect(() => {
		void batchSizeLiters;
		void efficiencyPercent;
		void boilTimeMinutes;
		if (batchParamsWatcherFirstRun) {
			batchParamsWatcherFirstRun = false;
			return;
		}
		if (inputsInitialized) {
			ingredientsDirty = true;
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
			color_srm: f.color_srm || 2,
			type: f.type ?? undefined
		}));

		// Extract-mode hops (Abstrax Quantum-style) are dosed cold-side by
		// volume and contribute no alpha-acid-based IBU, so they're
		// excluded from the IBU calculation. Their bittering profile is
		// captured separately on the extract spec, not via Tinseth.
		const calcHops: Hop[] = hops
			.filter((h) => !h.is_extract)
			.map((h) => ({
				name: h.name,
				amount_grams: h.amount_grams,
				alpha_acid_percent: h.alpha_acid_percent,
				boil_time_minutes: h.boil_time_minutes,
				form: h.form,
				// `use` may carry an extract-only long-form value
				// (e.g. add_to_package) on a stale row — cast through
				// the calculator's narrower union here. The filter
				// above ensures we never actually pass one through.
				use: h.use as Hop['use'],
				whirlpool_temp_c: h.whirlpool_temp_c
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
		ingredientsDirty = true;
	}

	function handleHopsUpdate(updated: RecipeHop[]) {
		hops = updated;
		ingredientsDirty = true;
	}

	function handleYeastSelect(yeast: YeastStrainResponse | null) {
		selectedYeast = yeast;
		ingredientsDirty = true;
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
			// "type" stays the BeerXML/BeerJSON brewery-type field (ale/lager/
			// all_grain). The style picker no longer writes to it — those
			// values come from import or the LLM save_recipe tool.
			type: '',
			style_id: selectedStyle?.id ?? null,
			style: styleInput,
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
			// Prefer brewer-declared imported targets when the user hasn't
			// edited ingredients since load — those are the recipe the
			// brewer wrote and the LLM should review them. Once ingredients
			// are dirty, the live calculator is the only honest signal
			// (tilt_ui-ak6 + codex review staleness fix).
			const useTargets = !ingredientsDirty;
			reviewResult = await reviewRecipe({
				name: name || 'Untitled Recipe',
				style: styleInput,
				og: useTargets ? initialData?.target_og ?? stats.og : stats.og,
				fg: useTargets ? initialData?.target_fg ?? stats.fg : stats.fg,
				abv: useTargets ? initialData?.target_abv ?? stats.abv : stats.abv,
				ibu: useTargets ? initialData?.target_ibu ?? stats.ibu : stats.ibu,
				color_srm: useTargets ? initialData?.target_srm ?? stats.srm : stats.srm,
				fermentables: fermentables.map((f) => ({
					name: f.name,
					amount_kg: f.amount_kg,
					color_srm: f.color_srm,
					type: f.type
				})),
				hops: hops.map((h) => ({
					name: h.name,
					amount_grams: h.is_extract ? 0 : h.amount_grams,
					// Don't expose dry-hop / mash duration as an IBU-time
					// to the LLM — it stores a day count converted to
					// minutes (4 days -> 5760) which the review prompt
					// would misread as an absurd boil duration. Extracts
					// are cold-side only, no boil time either.
					boil_time_minutes:
						h.is_extract ||
						h.use === 'dry_hop' ||
						h.use === 'mash' ||
						h.use === 'add_to_fermentation' ||
						h.use === 'add_to_package' ||
						h.use === 'package' ||
						h.use === 'keg' ||
						h.use === 'brite'
							? 0
							: h.boil_time_minutes,
					alpha_acid_percent: h.is_extract ? undefined : h.alpha_acid_percent,
					use: h.use,
					is_extract: Boolean(h.is_extract),
					amount_ml: h.is_extract ? h.amount_ml ?? null : null
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
		<div class="validation-error" role="alert">
			<svg class="error-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
				<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
			</svg>
			<span class="error-text">{validationError}</span>
			<button class="error-dismiss" onclick={() => (validationError = null)} aria-label="Dismiss">
				<svg fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
					<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
				</svg>
			</button>
		</div>
	{/if}

	<div class="workbench">
		<div class="main-col">
			<!-- Recipe Metadata -->
			<section class="block metadata-section">
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
							class:invalid={validationError !== null && !name.trim()}
							aria-invalid={validationError !== null && !name.trim() ? 'true' : undefined}
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
			</section>

			<!-- Batch Parameters -->
			<section class="block params-section">
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
							<span class="unit pct">%</span>
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
			</section>

			<!-- Fermentables -->
			<section class="block ingredient-section">
				<FermentableSelector
					{fermentables}
					{batchSizeLiters}
					{efficiencyPercent}
					onUpdate={handleFermentablesUpdate}
				/>
			</section>

			<!-- Hops -->
			<section class="block ingredient-section">
				<HopSelector hops={hops} og={recipeStats().og} {batchSizeLiters} onUpdate={handleHopsUpdate} />
			</section>

			<!-- Yeast -->
			<section class="block ingredient-section yeast-selector">
				<div class="selector-header yeast-header">
					<div class="header-left">
						<h3>Yeast</h3>
						{#if selectedYeast}
							<span class="stats">
								{#if selectedYeast.attenuation_low || selectedYeast.attenuation_high}
									<span class="stat">{selectedYeast.attenuation_low ?? '?'}&ndash;{selectedYeast.attenuation_high ?? '?'}% atten</span>
								{/if}
								{#if selectedYeast.temp_low || selectedYeast.temp_high}
									<span class="stat">{selectedYeast.temp_low ?? '?'}&ndash;{selectedYeast.temp_high ?? '?'}&thinsp;°C</span>
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
							&times;
						</button>
					</div>
				{/if}
			</section>

			<!-- Notes -->
			<section class="block notes-section">
				<h2 class="section-title"><label for="recipe-notes">Notes</label></h2>
				<textarea
					id="recipe-notes"
					bind:value={notes}
					placeholder="Brewing notes, tips, or variations..."
					rows="4"
					class="notes-input"
				></textarea>
			</section>
		</div>

		<!-- Live readings: always visible; top of page on phone, sticky rail on desk -->
		<aside class="rail" aria-label="Live recipe readings">
			{#if true}
				{@const stats = recipeStats()}
				<div class="rail-sticky">
					<RecipeStatsPanel
						og={stats.og}
						fg={stats.fg}
						abv={stats.abv}
						ibu={stats.ibu}
						colorSrm={stats.srm}
						{batchSizeLiters}
						styleName={selectedStyle?.name}
						styleCategory={selectedStyle?.category_number ? `${selectedStyle.category_number}${selectedStyle.style_letter ?? ''}` : undefined}
					/>

					<!-- Style Warnings (proactive BJCP validation) -->
					{#if styleWarnings().length > 0}
						<div class="style-warnings">
							<h2 class="section-title">Style Guidelines</h2>
							<ul class="warnings-list">
								{#each styleWarnings() as warning}
									<li class="warning-row {warning.severity}">
										<svg class="badge-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
											<circle cx="12" cy="12" r="10" />
											{#if warning.severity === 'error'}
												<path stroke-linecap="round" d="M15 9l-6 6M9 9l6 6" />
											{:else}
												<path stroke-linecap="round" d="M12 8v4M12 16h.01" />
											{/if}
										</svg>
										<span class="badge-stat">{warning.stat}</span>
										<span class="badge-value">{warning.value}</span>
										<span class="badge-target">outside {warning.range}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</div>
			{/if}
		</aside>
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
<RecipeReviewModal
	open={showReviewModal}
	loading={reviewLoading}
	error={reviewError}
	result={reviewResult}
	styleName={styleInput}
	onClose={closeReviewModal}
/>

<style>
	.recipe-builder {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	/* Validation error: danger text + outline + icon */
	.validation-error {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-sm) var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--status-danger);
		border-radius: 4px;
		color: var(--status-danger);
		font-size: var(--text-sm);
	}

	.validation-error .error-icon {
		width: 20px;
		height: 20px;
		flex-shrink: 0;
	}

	.validation-error .error-text {
		flex: 1;
		min-width: 0;
	}

	.validation-error .error-dismiss {
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

	.validation-error .error-dismiss:hover {
		border-color: var(--status-danger);
	}

	.validation-error .error-dismiss svg {
		width: 16px;
		height: 16px;
	}

	/* Workbench: phone/tablet single column with live readings first; desk two columns */
	.workbench {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 0 var(--space-xl);
	}

	.main-col,
	.rail {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.rail {
		order: -1;
	}

	.main-col > .block:first-child {
		border-top: none;
		padding-top: 0;
	}

	@media (min-width: 1041px) {
		.workbench {
			grid-template-columns: minmax(0, 1fr) 22rem;
			align-items: start;
		}

		.rail {
			order: 0;
		}

		.rail-sticky {
			position: sticky;
			top: var(--space-lg);
		}
	}

	/* Phone/tablet: keep the readings compact at the top */
	@media (max-width: 1040px) {
		.rail-sticky :global(.stats-panel) {
			margin-bottom: var(--space-md);
		}
	}

	.block {
		padding: var(--space-lg) 0;
		border-top: 1px solid var(--rule-hairline);
	}

	.section-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0 0 var(--space-sm) 0;
	}

	.section-title label {
		cursor: pointer;
	}

	/* Style guidelines */
	.style-warnings {
		padding-top: var(--space-xs);
	}

	.warnings-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.warning-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2xs) var(--space-xs);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	.warning-row .badge-icon {
		width: 16px;
		height: 16px;
		flex-shrink: 0;
		color: var(--status-warn);
	}

	.warning-row.error .badge-icon {
		color: var(--status-danger);
	}

	.badge-stat {
		font-weight: 600;
		color: var(--ink-primary);
	}

	.badge-value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		color: var(--ink-primary);
	}

	.badge-target {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	/* Form fields */
	.form-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-md);
	}

	.form-field {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		min-width: 0;
	}

	.form-field.full-width {
		grid-column: 1 / -1;
	}

	.form-field label,
	.param-field label {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
	}

	.form-input,
	.notes-input {
		width: 100%;
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-family: var(--font-body);
		font-size: var(--text-base);
		box-sizing: border-box;
	}

	.form-input::placeholder,
	.notes-input::placeholder {
		color: var(--ink-muted);
	}

	.form-input:focus-visible,
	.notes-input:focus-visible,
	.add-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	/* Invalid: danger border plus message in the alert above, not colour alone */
	.form-input.invalid {
		border-color: var(--status-danger);
		outline: 1px solid var(--status-danger);
	}

	.params-grid {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: var(--space-md);
	}

	.param-field {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		min-width: 0;
	}

	.input-with-unit {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.input-with-unit .form-input {
		min-width: 0;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		text-align: right;
	}

	.unit {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		min-width: 2ch;
	}

	.unit.pct {
		min-width: 2ch;
	}

	.notes-input {
		resize: vertical;
		line-height: 1.5;
	}

	/* Style autocomplete */
	.autocomplete-container {
		position: relative;
		display: flex;
		align-items: center;
	}

	.autocomplete-container .form-input {
		padding-right: 44px;
	}

	.autocomplete-spinner {
		position: absolute;
		right: 44px;
		width: 14px;
		height: 14px;
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
		.autocomplete-spinner {
			animation-duration: 2.4s;
		}
	}

	.clear-style {
		position: absolute;
		right: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		padding: 0;
		background: transparent;
		border: none;
		color: var(--ink-muted);
		font-size: 20px;
		line-height: 1;
		cursor: pointer;
	}

	.clear-style:hover {
		color: var(--ink-primary);
	}

	.clear-style:focus-visible,
	.style-option:focus-visible,
	.modal-close:focus-visible,
	.error-dismiss:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: -2px;
	}

	.style-dropdown {
		position: absolute;
		top: 100%;
		left: 0;
		right: 0;
		z-index: 20;
		margin: 2px 0 0;
		padding: 0;
		list-style: none;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		max-height: 320px;
		overflow-y: auto;
	}

	.style-dropdown li + li {
		border-top: 1px solid var(--rule-hairline);
	}

	.style-option {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
		width: 100%;
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: transparent;
		border: none;
		color: var(--ink-primary);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		text-align: left;
		cursor: pointer;
	}

	.style-option:hover {
		background: var(--bg-subtle);
	}

	.style-name {
		font-weight: 600;
	}

	.style-category {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		white-space: nowrap;
	}

	/* Yeast: same hairline vocabulary as the grain and hop selectors */
	.yeast-selector .selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding-bottom: var(--space-xs);
		border-bottom: 1px solid var(--rule-strong);
		margin-bottom: var(--space-sm);
	}

	.yeast-selector .header-left {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-md);
		min-width: 0;
	}

	.yeast-selector h3 {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-secondary);
		margin: 0;
	}

	.yeast-selector .stats {
		display: flex;
		gap: var(--space-sm);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.add-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 44px;
		padding: var(--space-xs) var(--space-md);
		background: transparent;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		white-space: nowrap;
		cursor: pointer;
		transition: border-color var(--transition), color var(--transition);
	}

	.add-btn:hover {
		border-color: var(--ink-secondary);
		color: var(--ink-primary);
	}

	.yeast-empty {
		padding: var(--space-md);
		border: 1px dashed var(--rule-strong);
		border-radius: 4px;
	}

	.yeast-empty p {
		color: var(--ink-secondary);
		font-size: var(--text-sm);
		margin: 0;
	}

	.yeast-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.yeast-main {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}

	.yeast-info {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}

	.yeast-name {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		overflow-wrap: anywhere;
	}

	.yeast-type {
		padding: 1px var(--space-xs);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}

	.yeast-details {
		display: flex;
		flex-wrap: wrap;
		gap: 0 var(--space-sm);
	}

	.yeast-details .detail {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.remove-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		padding: 0;
		background: transparent;
		color: var(--ink-muted);
		border: 1px solid transparent;
		border-radius: 4px;
		font-size: 20px;
		line-height: 1;
		cursor: pointer;
		flex-shrink: 0;
		transition: border-color var(--transition), color var(--transition);
	}

	.remove-btn:hover {
		border-color: var(--status-danger);
		color: var(--status-danger);
	}

	.remove-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	/* Yeast modal */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in oklch, var(--bg-canvas) 80%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-md);
	}

	.modal-content {
		width: 100%;
		max-width: 640px;
		max-height: 85vh;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 6px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.modal-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-sm) var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.modal-header h2 {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.modal-close {
		width: 44px;
		height: 44px;
		margin: -8px -12px -8px 0;
		padding: 0;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 4px;
		color: var(--ink-secondary);
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
	}

	.modal-close:hover {
		border-color: var(--rule-strong);
		color: var(--ink-primary);
	}

	.modal-body {
		padding: var(--space-md);
		overflow-y: auto;
	}

	@media (max-width: 760px) {
		.form-grid {
			grid-template-columns: minmax(0, 1fr);
		}

		.params-grid {
			grid-template-columns: repeat(3, minmax(0, 1fr));
			gap: var(--space-sm);
		}

		.input-with-unit {
			flex-direction: column;
			align-items: stretch;
			gap: 2px;
		}

		.input-with-unit .unit {
			text-align: right;
			font-size: var(--text-xs);
		}
	}
</style>
