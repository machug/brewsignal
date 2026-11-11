<script lang="ts">
	import { onMount } from 'svelte';
	import { goto } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse, RecipeReviewResponse } from '$lib/api';
	import { fetchRecipe, deleteRecipe, reviewRecipe } from '$lib/api';
	import FermentablesList from '$lib/components/recipe/FermentablesList.svelte';
	import HopSchedule from '$lib/components/recipe/HopSchedule.svelte';
	import OtherIngredients from '$lib/components/recipe/OtherIngredients.svelte';
	import MashSchedule from '$lib/components/recipe/MashSchedule.svelte';
	import FermentationSchedule from '$lib/components/recipe/FermentationSchedule.svelte';
	import WaterAdditions from '$lib/components/recipe/WaterAdditions.svelte';
	import RecipeStatsPanel from '$lib/components/recipe/RecipeStatsPanel.svelte';
	import RecipeReviewModal from '$lib/components/recipe/RecipeReviewModal.svelte';
	import RecipeBrewabilityBanner from '$lib/components/recipe/RecipeBrewabilityBanner.svelte';
	import ScaleRecipeDialog from '$lib/components/recipe/ScaleRecipeDialog.svelte';
	import { totalMashGrainKg } from '$lib/brewing/brewability';
	import { normalizeHopUse } from '$lib/components/recipe/RecipeBuilder.svelte';
	import { calculateWaterVolumes } from '$lib/utils/water';
	import { calculateRecipeStats, type Fermentable, type Hop, type Yeast, type BatchParams } from '$lib/brewing';

	let recipe = $state<RecipeResponse | null>(null);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let showDeleteConfirm = $state(false);
	let deleting = $state(false);

	// Scale dialog state
	let showScaleDialog = $state(false);
	let scaleTarget = $state<number | null>(null);

	// "Now" amounts for the scale preview — same source precedence as the
	// page display (format_extensions editor copy first, relationship rows
	// otherwise), so the preview matches what the user sees on the card.
	let scaleBeforeFermentables = $derived.by(() => {
		const ext = recipe?.format_extensions as
			| { fermentables?: Array<{ name?: string; amount_kg?: number | null }> }
			| undefined;
		const source = Array.isArray(ext?.fermentables) ? ext!.fermentables! : (recipe?.fermentables ?? []);
		return source.map((f) => ({ name: String(f.name ?? ''), amount_kg: f.amount_kg }));
	});


	function openScaleDialog(suggested?: number) {
		scaleTarget = suggested ?? null;
		showScaleDialog = true;
	}

	async function handleScaled() {
		if (recipeId) recipe = await fetchRecipe(recipeId);
	}

	// AI Review state
	let showReviewModal = $state(false);
	let reviewResult = $state<RecipeReviewResponse | null>(null);
	let reviewLoading = $state(false);
	let reviewError = $state<string | null>(null);

	// UI-created recipes carry fermentables in format_extensions while
	// recipe.fermentables may be empty — same precedence as liveStats below
	// (explicit empty array in format_extensions = deletion intent). Kettle
	// additions (extract/sugar/honey) never enter the mash, so they are
	// excluded from the grain total used for water and brewability math.
	let totalGrainKg = $derived.by(() => {
		const ext = recipe?.format_extensions as { fermentables?: Fermentable[] } | undefined;
		const fermentables = Array.isArray(ext?.fermentables)
			? ext!.fermentables!
			: (recipe?.fermentables ?? []);
		return totalMashGrainKg(fermentables);
	});

	let waterVolumes = $derived.by(() => {
		if (!recipe?.batch_size_liters || totalGrainKg <= 0) return null;
		return calculateWaterVolumes(recipe.batch_size_liters, totalGrainKg, recipe.boil_time_minutes, recipe.boil_size_l);
	});

	// Compute recipe stats live from ingredients so the detail page
	// matches the editor (and reflects the post-2.13.0 IBU model)
	// instead of showing stale stored DB values that may have been
	// computed under an older formula. Falls back to recipe.* when the
	// ingredient list is empty.
	let liveStats = $derived.by(() => {
		if (!recipe) return null;
		const ext = recipe.format_extensions as
			| { fermentables?: Fermentable[]; hops?: Array<Hop & { use?: string }> }
			| undefined;
		// format_extensions saves carry color_lovibond rather than
		// color_srm; calculateSRM needs color_srm and returns NaN
		// without it. Track whether ANY fermentable came in without a
		// usable color value so we can fall back to stored stats rather
		// than synthesizing a 0-SRM live result.
		const lovibondToSrm = (lov: number | undefined) =>
			lov != null ? 1.3546 * lov - 0.76 : undefined;
		let missingColor = false;
		// Explicit empty array in format_extensions is a deletion intent
		// (user removed all items); fall back to recipe.fermentables only
		// when format_extensions has no fermentables key at all.
		const fermentables: Fermentable[] = (
			Array.isArray(ext?.fermentables)
				? ext!.fermentables!.map((f) => {
						const srm =
							(f as { color_srm?: number }).color_srm ??
							lovibondToSrm((f as { color_lovibond?: number }).color_lovibond);
						if (srm == null) missingColor = true;
						return { ...f, color_srm: srm ?? 0 };
					})
				: (recipe.fermentables ?? []).map((f) => {
						if (f.color_srm == null) missingColor = true;
						return {
							name: f.name,
							amount_kg: f.amount_kg ?? 0,
							color_srm: f.color_srm ?? 0,
							type: f.type,
							potential_sg: f.yield_percent ? 1 + (f.yield_percent / 100) * 0.046 : undefined,
						};
					})
		) as Fermentable[];
		if (fermentables.length === 0) return null;

		// Extract-mode hops (Abstrax Quantum-style) are cold-side and
		// contribute no Tinseth IBU — skip them entirely so their wider
		// `use` allowlist (add_to_fermentation / add_to_package / etc.)
		// never has to round-trip through the IBU calculator's narrower
		// hot-side union.
		const rawHops: Array<Omit<Hop, 'use'> & { use?: string; is_extract?: boolean }> = Array.isArray(ext?.hops)
			? (ext!.hops! as Array<Omit<Hop, 'use'> & { use?: string; is_extract?: boolean }>)
			: (recipe.hops ?? []).map((h) => {
					const timing = h.timing || {};
					const tv = timing.duration?.value ?? timing.time?.value ?? 0;
					const tu = timing.duration?.unit ?? timing.time?.unit ?? 'min';
					const minutes = tu === 'day' ? tv * 24 * 60 : tv;
					return {
						name: h.name,
						amount_grams: h.amount_grams || 0,
						alpha_acid_percent: h.alpha_acid_percent || 0,
						boil_time_minutes: minutes,
						use: normalizeHopUse(timing.use) as string,
						form: (h.form || 'pellet') as 'pellet' | 'whole' | 'plug',
						is_extract: Boolean(h.is_extract),
						whirlpool_temp_c: timing.temperature?.value ?? null,
					};
				});
		const hops = rawHops
			.filter((h) => !h.is_extract)
			.map((h) => ({ ...h, use: normalizeHopUse(h.use) })) as Hop[];

		const yeast: Yeast = {
			name: recipe.yeast_name || '',
			attenuation_percent: recipe.yeast_attenuation ?? 75,
			temp_min_c: recipe.yeast_temp_min ?? 18,
			temp_max_c: recipe.yeast_temp_max ?? 22,
		};
		const batch: BatchParams = {
			batch_size_liters: recipe.batch_size_liters ?? 20,
			efficiency_percent: recipe.efficiency_percent ?? 72,
			boil_time_minutes: recipe.boil_time_minutes ?? 60,
		};
		const stats = calculateRecipeStats(fermentables, hops, yeast, batch);
		// If anything came back NaN (missing data, exotic units), fall
		// back to the stored stats rather than rendering NaN in the UI.
		// Also fall back on SRM if any fermentable was missing color
		// info — synthesizing 0 SRM would override valid stored color.
		const finite = (n: number | undefined) =>
			typeof n === 'number' && Number.isFinite(n) ? n : undefined;
		return {
			og: finite(stats.og),
			fg: finite(stats.fg),
			abv: finite(stats.abv),
			ibu: finite(stats.ibu),
			srm: missingColor ? undefined : finite(stats.srm),
		};
	});

	let recipeId = $derived.by(() => {
		const id = parseInt($page.params.id || '', 10);
		return isNaN(id) || id <= 0 ? null : id;
	});

	// Unified hop view that mirrors the liveStats precedence: prefer the
	// UI editor's format_extensions.hops copy (where new/edit pages save
	// their structured hop data including is_extract + amount_ml) and
	// fall back to recipe.hops (rows written by the LLM tool / import
	// path). Without this, UI-created extracts disappear from the AI
	// review payload and the HopSchedule render. Follow-up bead covers
	// teaching the backend POST/PUT to write recipe_hops directly.
	let displayHops = $derived.by(() => {
		if (!recipe) return [] as Array<Record<string, unknown>>;
		const ext = recipe.format_extensions as
			| { hops?: Array<Record<string, unknown>> }
			| undefined;
		// format_extensions.hops being an explicit array — even an empty
		// one — is the UI editor's authoritative copy. An empty array
		// means the brewer deleted every hop; falling back to recipe.hops
		// at that point would resurrect stale rows. Only fall back when
		// format_extensions has no hops key at all (importer / LLM path).
		if (Array.isArray(ext?.hops)) {
			return ext!.hops!.map((h) => {
				const minutes = Number(h.boil_time_minutes ?? 0);
				const use = String(h.use ?? '');
				const tempC = h.whirlpool_temp_c as number | null | undefined;
				return {
					name: h.name,
					amount_grams: h.amount_grams ?? 0,
					amount_ml: h.amount_ml ?? null,
					alpha_acid_percent: h.alpha_acid_percent ?? null,
					is_extract: Boolean(h.is_extract),
					form: h.form ?? null,
					origin: h.origin ?? null,
					use,
					boil_time_minutes: minutes,
					timing: {
						use,
						duration: { value: minutes, unit: 'min' },
						...(tempC != null ? { temperature: { value: tempC, unit: 'C' } } : {}),
					},
				};
			});
		}
		return (recipe.hops ?? []) as unknown as Array<Record<string, unknown>>;
	});

	let scaleBeforeHops = $derived(
		displayHops.map((h) => ({
			name: String(h.name ?? ''),
			amount_grams: (h.amount_grams as number | null) ?? null,
			amount_ml: (h.amount_ml as number | null) ?? null,
		}))
	);

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

	async function handleDelete() {
		if (!recipe) return;

		deleting = true;
		try {
			await deleteRecipe(recipe.id);
			goto('/recipes');
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete recipe';
			deleting = false;
			showDeleteConfirm = false;
		}
	}

	function handleBrewThis() {
		if (!recipe) return;
		goto(`/batches/new?recipe_id=${recipe.id}`);
	}

	async function handleReview() {
		if (!recipe) return;

		// BJCP style FK now drives the style label (tilt_ui-tre);
		// recipe.type is the BeerXML brewery-type column and may be
		// missing entirely on UI-created recipes. Prefer the linked
		// style name, fall back to type for legacy recipes.
		const styleName = recipe.style?.name ?? recipe.type ?? '';
		if (!styleName.trim()) {
			reviewError = 'Recipe is missing a beer style — edit the recipe and add one to get an AI review';
			showReviewModal = true;
			return;
		}

		// UI editor saves fermentables under format_extensions; the
		// recipe.fermentables table rows are only populated by import or
		// the LLM save_recipe path. Mirror the liveStats precedence.
		const ext = recipe.format_extensions as
			| { fermentables?: Array<{ name?: string; amount_kg?: number; color_srm?: number; color_lovibond?: number; type?: string }> }
			| undefined;
		const fermentables = Array.isArray(ext?.fermentables)
			? ext!.fermentables!
			: recipe.fermentables ?? [];
		if (fermentables.length === 0) {
			reviewError = 'Recipe has no fermentables to review';
			showReviewModal = true;
			return;
		}

		reviewLoading = true;
		reviewError = null;
		reviewResult = null;
		showReviewModal = true;

		try {
			const stats = liveStats;
			// Review what the card actually shows. The stats card binds
			// `liveStats?.X ?? recipe.X` (see RecipeStatsPanel props below), so
			// the review payload must use the SAME precedence — otherwise the
			// user sees e.g. IBU 36 on the card but "reviewed as 27"
			// (tilt_ui-gkm). target_* is only the small "src" hint, so it's the
			// last fallback, never preferred over the displayed value.
			const og = stats?.og ?? recipe.og ?? recipe.target_og ?? 1.05;
			const fg = stats?.fg ?? recipe.fg ?? recipe.target_fg ?? 1.01;
			const abv = stats?.abv ?? recipe.abv ?? recipe.target_abv ?? 5.0;
			const ibu = stats?.ibu ?? recipe.ibu ?? recipe.target_ibu ?? 30;
			const colorSrm = stats?.srm ?? recipe.color_srm ?? recipe.target_srm ?? 8;

			reviewResult = await reviewRecipe({
				name: recipe.name || 'Untitled Recipe',
				style: styleName,
				og,
				fg,
				abv,
				ibu,
				color_srm: colorSrm,
				fermentables: fermentables.map((f) => ({
					name: (f as { name?: string }).name ?? '',
					amount_kg: (f as { amount_kg?: number }).amount_kg ?? 0,
					// format_extensions.fermentables carries color_lovibond
					// while recipe.fermentables uses color_srm. Convert
					// Lovibond → SRM (1.3546*L − 0.76) when only Lovibond
					// is available.
					color_srm:
						(f as { color_srm?: number }).color_srm ??
						((f as { color_lovibond?: number }).color_lovibond != null
							? 1.3546 * (f as { color_lovibond: number }).color_lovibond - 0.76
							: undefined),
					type: (f as { type?: string }).type
				})),
				// displayHops merges format_extensions.hops (UI editor copy
				// with is_extract + amount_ml) with the recipe_hops table
				// fallback. Extracts come through with amount_grams=0 and
				// no alpha, so the IBU side of the review prompt naturally
				// ignores them while the agent still sees them as part of
				// the hop bill (so it can comment on aroma additions and
				// Abstrax usage). The backend review tool already knows
				// is_extract semantics from phase 1.
				hops: displayHops.map((h: Record<string, unknown>) => {
					const timing = (h.timing as Record<string, any>) || {};
					const tv = timing.duration?.value ?? timing.time?.value ?? 0;
					const tu = timing.duration?.unit ?? timing.time?.unit ?? 'min';
					const minutes = tu === 'day' ? tv * 24 * 60 : tv;
					const isExtract = Boolean(h.is_extract);
					// Normalise the use under the same isExtract flag the
					// payload carries, otherwise extract-only cold-side
					// uses (add_to_fermentation/add_to_package/keg/brite)
					// collapse to "boil" and the LLM sees an aroma extract
					// dosed at boil time.
					const use = normalizeHopUse(
						timing.use ?? (h.use as string | undefined),
						isExtract,
					);
					const alpha = h.alpha_acid_percent;
					const ml = h.amount_ml;
					return {
						name: h.name as string,
						amount_grams: Number(h.amount_grams ?? 0),
						// Don't expose dry-hop / mash duration as IBU-time
						// to the LLM — the review prompt would misread a
						// 4-day dry hop as an absurd boil duration.
						// Extracts are cold-side only, so always zero.
						boil_time_minutes:
							isExtract || use === 'dry_hop' || use === 'mash' ? 0 : Number(minutes),
						alpha_acid_percent: typeof alpha === 'number' ? alpha : undefined,
						use,
						is_extract: isExtract,
						amount_ml: typeof ml === 'number' ? ml : null
					};
				}),
				yeast: recipe.yeast_name
					? {
							name: recipe.yeast_name,
							producer: recipe.yeast_lab ?? undefined,
							attenuation: recipe.yeast_attenuation ?? undefined
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

<svelte:head>
	<title>{recipe?.name || 'Recipe'} | BrewSignal</title>
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

	{#if loading}
		<div class="state-block">
			<div class="spinner"></div>
			<p>Loading recipe...</p>
		</div>
	{:else if error}
		<div class="state-block">
			<p class="error-message">{error}</p>
		</div>
	{:else if recipe}
		<!-- Header -->
		<header class="recipe-hero">
			<div class="hero-title-area">
				<h1 class="recipe-title">{recipe.name}</h1>
				<div class="recipe-meta">
					{#if recipe.type}
						<span class="meta-pill">{recipe.type}</span>
					{/if}
					{#if recipe.author}
						<span class="meta-author">by {recipe.author}</span>
					{/if}
				</div>
			</div>
			<div class="header-actions">
				<button
					type="button"
					class="btn-secondary"
					onclick={handleReview}
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
					class="btn-secondary"
					onclick={() => openScaleDialog()}
					disabled={!recipe.batch_size_liters}
					title={recipe.batch_size_liters ? 'Scale recipe to a new batch size' : 'Recipe has no batch size to scale from'}
				>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
					</svg>
					Scale
				</button>
				<a href="/recipes/{recipe.id}/edit" class="btn-secondary">
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
					</svg>
					Edit
				</a>
				<a href="/api/recipes/{recipe.id}/export/brewfather?download=true" class="btn-secondary" download>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
					</svg>
					Export
				</a>
				<button type="button" class="btn-primary" onclick={handleBrewThis}>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
					</svg>
					Brew This
				</button>
				<button type="button" class="btn-ghost-danger" onclick={() => (showDeleteConfirm = true)} aria-label="Delete recipe">
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
					</svg>
				</button>
			</div>
		</header>

		<!-- Stats strip with SRM glass -->
		<RecipeStatsPanel
			og={liveStats?.og ?? recipe.og ?? 1.050}
			fg={liveStats?.fg ?? recipe.fg ?? 1.010}
			abv={liveStats?.abv ?? recipe.abv ?? 5.0}
			ibu={liveStats?.ibu ?? recipe.ibu ?? 30}
			colorSrm={liveStats?.srm ?? recipe.color_srm ?? 8}
			batchSizeLiters={recipe.batch_size_liters ?? 20}
			styleName={recipe.style?.name}
			styleCategory={recipe.style?.category_number ? `${recipe.style.category_number}${recipe.style.style_letter ?? ''}` : undefined}
			targetOg={recipe.target_og}
			targetFg={recipe.target_fg}
			targetAbv={recipe.target_abv}
			targetIbu={recipe.target_ibu}
			targetSrm={recipe.target_srm}
		/>

		<RecipeBrewabilityBanner
			batchSizeLiters={recipe.batch_size_liters}
			{totalGrainKg}
			boilTimeMinutes={recipe.boil_time_minutes}
			boilSizeL={recipe.boil_size_l}
			onScaleToFit={(suggested) => openScaleDialog(suggested)}
		/>

		<ScaleRecipeDialog
			open={showScaleDialog}
			recipeId={recipe.id}
			currentBatchLiters={recipe.batch_size_liters ?? 0}
			fermentables={scaleBeforeFermentables}
			hops={scaleBeforeHops}
			initialTarget={scaleTarget}
			onClose={() => (showScaleDialog = false)}
			onScaled={handleScaled}
			onBigJumpScaled={handleReview}
		/>

		<div class="recipe-content">
			<!-- Fermentables Section -->
			{#if recipe.fermentables && recipe.fermentables.length > 0}
				<section class="block">
					<FermentablesList fermentables={recipe.fermentables} />
				</section>
			{/if}

			<!-- Hops Section -->
			{#if displayHops.length > 0}
				<section class="block">
					<HopSchedule hops={displayHops as never} />
				</section>
			{/if}

			<!-- Yeast Section -->
			{#if recipe.yeast_name}
				<section class="block">
					<h2 class="section-title">Yeast</h2>
					<div class="table-scroll">
						<table class="spec-table">
							<thead>
								<tr>
									<th>Strain</th>
									<th>Lab</th>
									<th class="num">Temp Range</th>
									<th class="num">Attenuation</th>
								</tr>
							</thead>
							<tbody>
								<tr>
									<td class="name">{recipe.yeast_name}</td>
									<td class="muted">{recipe.yeast_lab ?? '--'}</td>
									<td class="num">
										{#if recipe.yeast_temp_min != null && recipe.yeast_temp_max != null}
											{recipe.yeast_temp_min.toFixed(0)}–{recipe.yeast_temp_max.toFixed(0)}&thinsp;°C
										{:else}--{/if}
									</td>
									<td class="num">{recipe.yeast_attenuation ? `${recipe.yeast_attenuation.toFixed(0)} %` : '--'}</td>
								</tr>
							</tbody>
						</table>
					</div>
				</section>
			{/if}

			<!-- Other Ingredients (non-water miscs: finings, enzymes, spices) -->
			{#if (recipe.miscs || []).some((m) => (m.type ?? '').toLowerCase().replace('_', ' ') !== 'water agent')}
				<section class="block">
					<OtherIngredients miscs={recipe.miscs || []} />
				</section>
			{/if}

			<!-- Mash Schedule Section -->
			{#if recipe.mash_steps && recipe.mash_steps.length > 0}
				<section class="block">
					<MashSchedule steps={recipe.mash_steps} />
				</section>
			{/if}

			<!-- Fermentation Schedule Section -->
			{#if recipe.fermentation_steps && recipe.fermentation_steps.length > 0}
				<section class="block">
					<FermentationSchedule steps={recipe.fermentation_steps} />
				</section>
			{/if}

			<!-- Water Additions Section -->
			{#if (recipe.miscs && recipe.miscs.length > 0) || (recipe.water_profiles && recipe.water_profiles.length > 0) || (recipe.water_adjustments && recipe.water_adjustments.length > 0)}
				<section class="block">
					<WaterAdditions
						miscs={recipe.miscs || []}
						waterProfiles={recipe.water_profiles || []}
						waterAdjustments={recipe.water_adjustments || []}
					/>
				</section>
			{/if}

			<!-- Water Volumes (calculated from grain bill + batch size) -->
			{#if waterVolumes}
				<section class="block">
					<h2 class="section-title">Water</h2>
					<dl class="readouts">
						<div class="readout">
							<dt>Mash water</dt>
							<dd>{waterVolumes.mashWater.toFixed(2)}&thinsp;L</dd>
						</div>
						<div class="readout">
							<dt>Sparge water</dt>
							<dd>{waterVolumes.spargeWater.toFixed(2)}&thinsp;L</dd>
						</div>
						<div class="readout total">
							<dt>Total water</dt>
							<dd>{waterVolumes.totalWater.toFixed(2)}&thinsp;L</dd>
						</div>
						<div class="readout">
							<dt>Mash volume (water + grain)</dt>
							<dd>{waterVolumes.mashVolume.toFixed(2)}&thinsp;L</dd>
						</div>
					</dl>
				</section>
			{/if}

			<!-- Batch Details -->
			{#if recipe.batch_size_liters || recipe.efficiency_percent || recipe.boil_time_minutes}
				<section class="block">
					<h2 class="section-title">Batch Details</h2>
					<dl class="readouts">
						{#if recipe.batch_size_liters}
							<div class="readout">
								<dt>Batch size</dt>
								<dd>{recipe.batch_size_liters.toFixed(1)}&thinsp;L</dd>
							</div>
						{/if}
						{#if recipe.efficiency_percent}
							<div class="readout">
								<dt>Efficiency</dt>
								<dd>{recipe.efficiency_percent.toFixed(0)}&thinsp;%</dd>
							</div>
						{/if}
						{#if recipe.boil_time_minutes}
							<div class="readout">
								<dt>Boil time</dt>
								<dd>{recipe.boil_time_minutes}&thinsp;min</dd>
							</div>
						{/if}
					</dl>
				</section>
			{/if}

			<!-- Notes Section -->
			{#if recipe.notes}
				<section class="block">
					<h2 class="section-title">Notes</h2>
					<div class="notes-content">
						{#each recipe.notes.split('\n') as line}
							{#if line.trim()}
								<p>{line}</p>
							{:else}
								<br />
							{/if}
						{/each}
					</div>
				</section>
			{/if}

			<!-- Footer -->
			<div class="recipe-footer">
				<span class="created-date">Created {new Date(recipe.created_at).toLocaleDateString('en-AU', { day: 'numeric', month: 'short', year: 'numeric' })}</span>
			</div>
		</div>
	{/if}
</div>

<!-- AI Review Modal -->
<RecipeReviewModal
	open={showReviewModal}
	loading={reviewLoading}
	error={reviewError}
	result={reviewResult}
	styleName={recipe?.style?.name ?? recipe?.type ?? ''}
	onClose={closeReviewModal}
/>

<!-- Delete Confirmation Modal -->
{#if showDeleteConfirm}
	<div
		class="modal-overlay"
		onclick={() => (showDeleteConfirm = false)}
		onkeydown={(e) => e.key === 'Escape' && (showDeleteConfirm = false)}
		role="presentation"
		aria-hidden="true"
	>
		<div
			class="modal"
			onclick={(e) => e.stopPropagation()}
			onkeydown={(e) => e.stopPropagation()}
			role="dialog"
			aria-modal="true"
			aria-labelledby="delete-recipe-title"
		>
			<div class="modal-header">
				<svg class="modal-icon danger" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
				</svg>
				<h2 id="delete-recipe-title" class="modal-title">Delete Recipe?</h2>
			</div>
			<p class="modal-text">
				Are you sure you want to delete <strong>"{recipe?.name}"</strong>? This action cannot be undone.
			</p>
			<div class="modal-actions">
				<button
					type="button"
					class="modal-btn cancel"
					onclick={() => (showDeleteConfirm = false)}
					disabled={deleting}
				>
					Cancel
				</button>
				<button type="button" class="modal-btn delete" onclick={handleDelete} disabled={deleting}>
					{#if deleting}
						<span class="btn-spinner"></span>
						Deleting...
					{:else}
						Delete Recipe
					{/if}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container {
		max-width: 1100px;
		margin: 0 auto;
		padding: var(--space-lg);
	}

	/* Back Link */
	.back-link {
		margin-bottom: var(--space-md);
	}

	.back-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-xs);
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

	/* Loading & Error States */
	.state-block {
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

	.state-block p {
		margin: 0;
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
		to { transform: rotate(360deg); }
	}

	@media (prefers-reduced-motion: reduce) {
		.spinner,
		.btn-spinner {
			animation-duration: 2.4s;
		}
	}

	.error-message {
		color: var(--status-danger);
		font-size: var(--text-sm);
	}

	/* Header */
	.recipe-hero {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-md);
		flex-wrap: wrap;
		margin-bottom: var(--space-lg);
	}

	.hero-title-area {
		flex: 1 1 280px;
		min-width: 0;
	}

	.recipe-title {
		font-family: var(--font-display);
		font-size: var(--text-xl);
		font-weight: 600;
		letter-spacing: -0.01em;
		color: var(--ink-primary);
		margin: 0 0 var(--space-xs) 0;
		line-height: 1.2;
		overflow-wrap: anywhere;
	}

	.recipe-meta {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		flex-wrap: wrap;
	}

	/* Outlined uppercase status pill */
	.meta-pill {
		display: inline-flex;
		align-items: center;
		padding: 2px var(--space-xs);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--accent);
		border: 1px solid var(--accent-rule);
		border-radius: 4px;
	}

	.meta-author {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* Header Actions */
	.header-actions {
		display: flex;
		gap: var(--space-xs);
		align-items: center;
		flex-wrap: wrap;
	}

	.btn-icon {
		width: 16px;
		height: 16px;
	}

	.btn-secondary,
	.btn-primary {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		padding: var(--space-xs) var(--space-md);
		min-height: 36px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		border-radius: 4px;
		text-decoration: none;
		cursor: pointer;
		transition: background var(--transition), border-color var(--transition), color var(--transition);
	}

	.btn-secondary {
		background: transparent;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}

	.btn-secondary:hover:not(:disabled) {
		border-color: var(--accent-rule);
		color: var(--ink-primary);
	}

	.btn-secondary:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-primary {
		background: var(--accent);
		border: 1px solid var(--accent);
		color: var(--accent-ink);
	}

	.btn-primary:hover {
		background: var(--accent-hover);
		border-color: var(--accent-hover);
	}

	.btn-ghost-danger {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		padding: 0;
		background: transparent;
		border: 1px solid transparent;
		border-radius: 4px;
		color: var(--ink-muted);
		cursor: pointer;
		transition: border-color var(--transition), color var(--transition), background var(--transition);
	}

	.btn-ghost-danger:hover {
		border-color: var(--status-danger);
		color: var(--status-danger);
	}

	.btn-secondary:focus-visible,
	.btn-primary:focus-visible,
	.btn-ghost-danger:focus-visible,
	.back-btn:focus-visible,
	.modal-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	/* Content: hairline-separated sections, no cards */
	.recipe-content {
		display: flex;
		flex-direction: column;
	}

	.block {
		padding: var(--space-lg) 0;
		border-top: 1px solid var(--rule-hairline);
	}

	.section-title {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0 0 var(--space-sm) 0;
	}

	/* Yeast table */
	.table-scroll {
		overflow-x: auto;
	}

	.spec-table {
		width: 100%;
		min-width: 420px;
		border-collapse: collapse;
	}

	.spec-table th {
		text-align: left;
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-strong);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		white-space: nowrap;
	}

	.spec-table td {
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}

	.spec-table .num {
		text-align: right;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	.spec-table th.num {
		font-family: var(--font-body);
	}

	.spec-table .name {
		font-weight: 600;
	}

	.spec-table .muted {
		color: var(--ink-secondary);
	}

	/* Readouts (batch details, water volumes): hairline instrument row */
	.readouts {
		display: flex;
		flex-wrap: wrap;
		margin: 0;
		border-top: 1px solid var(--rule-hairline);
		border-left: 1px solid var(--rule-hairline);
		overflow: hidden;
	}

	.readout {
		flex: 1 1 140px;
		display: flex;
		flex-direction: column;
		gap: 2px;
		padding: var(--space-sm) var(--space-md);
		border-right: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
		margin: 0 -1px -1px 0;
		min-width: 0;
	}

	.readout dt {
		order: 1;
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}

	.readout dd {
		order: 2;
		margin: 0;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-lg);
		font-weight: 500;
		color: var(--ink-primary);
	}

	.readout.total dd {
		color: var(--accent);
	}

	/* Notes */
	.notes-content {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.7;
		max-width: 70ch;
	}

	.notes-content p {
		margin: 0 0 var(--space-sm) 0;
	}

	.notes-content p:last-child {
		margin-bottom: 0;
	}

	/* Footer */
	.recipe-footer {
		padding-top: var(--space-md);
		border-top: 1px solid var(--rule-hairline);
	}

	.created-date {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
	}

	/* Delete modal */
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

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 6px;
		padding: var(--space-lg);
		max-width: 400px;
		width: 100%;
	}

	.modal-header {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-bottom: var(--space-md);
	}

	.modal-icon {
		width: 24px;
		height: 24px;
		flex-shrink: 0;
	}

	.modal-icon.danger {
		color: var(--status-danger);
	}

	.modal-title {
		font-family: var(--font-display);
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.modal-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		line-height: 1.6;
		margin: 0 0 var(--space-lg) 0;
	}

	.modal-text strong {
		color: var(--ink-primary);
	}

	.modal-actions {
		display: flex;
		gap: var(--space-sm);
		justify-content: flex-end;
	}

	.modal-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: var(--space-xs);
		padding: var(--space-xs) var(--space-md);
		min-height: 36px;
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		cursor: pointer;
		transition: background var(--transition), border-color var(--transition);
		min-width: 100px;
	}

	.modal-btn.cancel {
		background: transparent;
		border: 1px solid var(--rule-strong);
		color: var(--ink-primary);
	}

	.modal-btn.cancel:hover {
		background: var(--bg-subtle);
	}

	/* Destructive action: outlined, danger ink */
	.modal-btn.delete {
		background: transparent;
		border: 1px solid var(--status-danger);
		color: var(--status-danger);
	}

	.modal-btn.delete:hover:not(:disabled) {
		background: var(--negative-muted);
	}

	.modal-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-spinner {
		width: 14px;
		height: 14px;
		border: 2px solid currentColor;
		border-top-color: transparent;
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	/* Phone */
	@media (max-width: 640px) {
		.page-container {
			padding: var(--space-md);
		}

		.header-actions {
			width: 100%;
		}

		.header-actions .btn-secondary,
		.header-actions .btn-primary {
			flex: 1 1 calc(33% - var(--space-xs));
			min-width: 0;
			padding-inline: var(--space-sm);
		}
	}
</style>
