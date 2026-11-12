<script lang="ts">
	import { recipeUrl } from '$lib/urls';
	import { onMount } from 'svelte';
	import { goto, replaceState } from '$app/navigation';
	import { page } from '$app/stores';
	import type { RecipeResponse, SavedReview, SavedReviewSummary } from '$lib/api';
	import { fetchRecipe, deleteRecipe, fetchRecipeReview, fetchRecipeReviews, runRecipeReview } from '$lib/api';
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

	// Phone "More" action menu
	let moreOpen = $state(false);
	let moreWrap = $state<HTMLElement | null>(null);
	let moreBtn = $state<HTMLButtonElement | null>(null);

	function toggleMore() {
		moreOpen = !moreOpen;
		if (moreOpen) {
			// Move focus into the menu once it is rendered
			queueMicrotask(() => moreWrap?.querySelector<HTMLElement>('.menu-item:not(:disabled)')?.focus());
		}
	}

	function closeMore(restoreFocus = false) {
		if (!moreOpen) return;
		moreOpen = false;
		if (restoreFocus) moreBtn?.focus();
	}

	function onMoreKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && moreOpen) {
			e.stopPropagation();
			closeMore(true);
		}
	}

	function onMoreFocusout(e: FocusEvent) {
		const next = e.relatedTarget as Node | null;
		if (moreOpen && next && !moreWrap?.contains(next)) moreOpen = false;
	}

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
	let reviewResult = $state<SavedReview | null>(null);
	let reviewHistory = $state<SavedReviewSummary[]>([]);
	let currentFingerprint = $state('');
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

	// Show the readable URL (/recipes/25-west-coast-ipa) without a reload,
	// also after a rename; the leading id is what the page reads (tilt_ui-9hg).
	$effect(() => {
		if (!recipe) return;
		const path = recipeUrl(recipe);
		// Compare with the real address: shallow replaceState does not update
		// $page.url, and reading $page here would re-run this effect in a loop.
		if (location.pathname !== path) replaceState(path + location.search + location.hash, {});
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

	// Saved reviews (tilt_ui-de6v): open the latest one; only run the AI when there is none
	// or the user asks for a re-review. The backend reads the full stored recipe.
	async function loadReviewHistory(id: number) {
		const h = await fetchRecipeReviews(id);
		reviewHistory = h.reviews;
		currentFingerprint = h.current_fingerprint;
	}

	async function handleReview() {
		if (!recipe) return;
		const id = recipe.id;
		showReviewModal = true;
		reviewError = null;
		reviewResult = null;
		reviewLoading = true;
		try {
			await loadReviewHistory(id);
			const latest = reviewHistory.length ? await fetchRecipeReview(id, reviewHistory[0].id) : await runRecipeReview(id);
			if (!showReviewModal || recipe?.id !== id) return; // closed or navigated away meanwhile
			reviewResult = latest;
			if (!reviewHistory.length) await loadReviewHistory(id);
		} catch (err) {
			reviewError = err instanceof Error ? err.message : 'Failed to get AI review';
		} finally {
			reviewLoading = false;
		}
	}

	async function rereview() {
		if (!recipe) return;
		const id = recipe.id;
		reviewError = null;
		reviewLoading = true;
		try {
			reviewResult = await runRecipeReview(id);
			await loadReviewHistory(id);
		} catch (err) {
			reviewError = err instanceof Error ? err.message : 'Failed to get AI review';
		} finally {
			reviewLoading = false;
		}
	}

	async function selectReview(reviewId: number) {
		if (!recipe) return;
		reviewError = null;
		try {
			reviewResult = await fetchRecipeReview(recipe.id, reviewId);
		} catch (err) {
			reviewError = err instanceof Error ? err.message : 'Failed to load review';
		}
	}

	function closeReviewModal() {
		showReviewModal = false;
		reviewResult = null;
		reviewError = null;
		reviewHistory = [];
		currentFingerprint = '';
	}
</script>

<svelte:window onclick={(e) => { if (moreOpen && moreWrap && !moreWrap.contains(e.target as Node)) moreOpen = false; }} />

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
				<button type="button" class="btn-primary act-brew" onclick={handleBrewThis}>
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
					</svg>
					Brew This
				</button>
				<a href="{recipeUrl(recipe)}/edit" class="btn-secondary act-edit">
					<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
					</svg>
					Edit
				</a>
				<!-- Desk: these render inline (display: contents). Phone: they live in the More menu. -->
				<div class="more-wrap" bind:this={moreWrap} onkeydown={onMoreKeydown} onfocusout={onMoreFocusout} role="presentation">
					<button
						type="button"
						class="btn-secondary more-btn"
						aria-haspopup="true"
						aria-expanded={moreOpen}
						aria-controls="recipe-more-menu"
						bind:this={moreBtn}
						onclick={toggleMore}
					>
						More
						<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
						</svg>
					</button>
					<div id="recipe-more-menu" class="more-menu" class:open={moreOpen}>
						<button
							type="button"
							class="btn-secondary menu-item act-review"
							onclick={() => { closeMore(); handleReview(); }}
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
							class="btn-secondary menu-item act-scale"
							onclick={() => { closeMore(); openScaleDialog(); }}
							disabled={!recipe.batch_size_liters}
							title={recipe.batch_size_liters ? 'Scale recipe to a new batch size' : 'Recipe has no batch size to scale from'}
						>
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
							</svg>
							Scale
						</button>
						<a href="/api/recipes/{recipe.id}/export/brewfather?download=true" class="btn-secondary menu-item act-export" download onclick={() => closeMore()}>
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
							</svg>
							Export
						</a>
						<button type="button" class="btn-ghost-danger menu-item act-delete" onclick={() => { closeMore(); showDeleteConfirm = true; }} aria-label="Delete recipe">
							<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
								<path stroke-linecap="round" stroke-linejoin="round" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
							</svg>
							<span class="menu-label">Delete</span>
						</button>
					</div>
				</div>
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

		<div class="workbench">
		<div class="main-col">
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
									<th class="col-sec">Lab</th>
									<th class="num">Temp Range</th>
									<th class="num">Attenuation</th>
								</tr>
							</thead>
							<tbody>
								<tr>
									<td class="name">{recipe.yeast_name}{#if recipe.yeast_lab}<div class="sec-inline">{recipe.yeast_lab}</div>{/if}</td>
									<td class="muted col-sec">{recipe.yeast_lab ?? '--'}</td>
									<td class="num">
										{#if recipe.yeast_temp_min != null && recipe.yeast_temp_max != null}
											{recipe.yeast_temp_min.toFixed(0)}–{recipe.yeast_temp_max.toFixed(0)}&thinsp;°C
										{:else}--{/if}
									</td>
									<td class="num">{recipe.yeast_attenuation ? `${recipe.yeast_attenuation.toFixed(0)}%` : '--'}</td>
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

		</div>

		<aside class="rail">
			<!-- Batch Details -->
			{#if recipe.batch_size_liters || recipe.efficiency_percent || recipe.boil_time_minutes}
				<section class="block">
					<h2 class="section-title">Batch Details</h2>
					<dl class="readouts">
						{#if recipe.batch_size_liters}
							<div class="readout">
								<dt>Batch size</dt>
								<dd>{recipe.batch_size_liters.toFixed(1)}<span class="unit">L</span></dd>
							</div>
						{/if}
						{#if recipe.efficiency_percent}
							<div class="readout">
								<dt>Efficiency</dt>
								<dd>{recipe.efficiency_percent.toFixed(0)}<span class="unit pct">%</span></dd>
							</div>
						{/if}
						{#if recipe.boil_time_minutes}
							<div class="readout">
								<dt>Boil time</dt>
								<dd>{recipe.boil_time_minutes}<span class="unit">min</span></dd>
							</div>
						{/if}
					</dl>
				</section>
			{/if}

			<!-- Water Volumes (calculated from grain bill + batch size) -->
			{#if waterVolumes}
				<section class="block">
					<h2 class="section-title">Water</h2>
					<dl class="readouts">
						<div class="readout">
							<dt>Mash water</dt>
							<dd>{waterVolumes.mashWater.toFixed(2)}<span class="unit">L</span></dd>
						</div>
						<div class="readout">
							<dt>Sparge water</dt>
							<dd>{waterVolumes.spargeWater.toFixed(2)}<span class="unit">L</span></dd>
						</div>
						<div class="readout">
							<dt>Total water</dt>
							<dd>{waterVolumes.totalWater.toFixed(2)}<span class="unit">L</span></dd>
						</div>
						<div class="readout">
							<dt>Mash volume (water + grain)</dt>
							<dd>{waterVolumes.mashVolume.toFixed(2)}<span class="unit">L</span></dd>
						</div>
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

		</aside>
		</div>

		<div class="recipe-content">
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
	history={reviewHistory}
	{currentFingerprint}
	onRereview={rereview}
	onSelect={selectReview}
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
		color: var(--ink-secondary);
		background: transparent;
		border: 1px solid var(--rule-strong);
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
		flex-shrink: 0;
	}

	/* Desk: More wrapper dissolves; actions keep their original order */
	.more-wrap,
	.more-menu {
		display: contents;
	}

	.btn-secondary.more-btn,
	.menu-label {
		display: none;
	}

	.act-review { order: 1; }
	.act-scale { order: 2; }
	.act-edit { order: 3; }
	.act-export { order: 4; }
	.act-brew { order: 5; }
	.act-delete { order: 6; }

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
		white-space: nowrap;
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
		border-color: var(--ink-secondary);
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

	.main-col > .block:first-child,
	.rail > .block:first-child {
		border-top: none;
		padding-top: 0;
	}

	.recipe-content {
		display: flex;
		flex-direction: column;
	}

	/* Desk: ingredient tables in the main column, secondary readings in the right rail */
	@media (min-width: 1041px) {
		.page-container {
			max-width: 1280px;
		}

		.workbench {
			grid-template-columns: minmax(0, 1fr) 22rem;
		}
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

	.spec-table th:first-child,
	.spec-table td:first-child {
		padding-left: 0;
	}

	.spec-table th:last-child,
	.spec-table td:last-child {
		padding-right: 0;
	}

	.sec-inline {
		display: none;
		color: var(--ink-muted);
		font-size: var(--text-xs);
		font-weight: 400;
		margin-top: 2px;
	}

	/* Readouts (batch details, water volumes): hairline instrument row */
	.readouts {
		display: flex;
		flex-wrap: wrap;
		margin: 0;
		background: var(--bg-surface);
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
		font-size: var(--text-xl);
		font-weight: 500;
		line-height: 1.2;
		color: var(--ink-primary);
	}

	.unit {
		margin-left: 0.25em;
		font-size: 0.875rem;
		font-weight: 400;
		color: var(--ink-muted);
	}

	.unit.pct {
		margin-left: 0;
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

	/* Phone and tablet action menu */
	@media (max-width: 760px) {
		.page-container {
			padding: var(--space-md);
		}

		.header-actions {
			width: 100%;
			flex-wrap: nowrap;
		}

		.btn-secondary,
		.btn-primary,
		.modal-btn {
			min-height: 44px;
		}

		.spec-table {
			min-width: 0;
		}

		.col-sec {
			display: none;
		}

		.sec-inline {
			display: block;
		}

		.act-brew,
		.act-edit,
		.more-btn {
			flex: 1 1 0;
			min-width: 0;
			padding-inline: var(--space-sm);
		}

		.act-brew,
		.act-edit {
			order: 0;
		}

		.more-wrap {
			display: block;
			position: relative;
			flex: 1 1 0;
			min-width: 0;
		}

		.btn-secondary.more-btn {
			display: inline-flex;
			width: 100%;
		}

		.more-menu {
			display: none;
			position: absolute;
			right: 0;
			top: calc(100% + var(--space-2xs));
			z-index: 30;
			min-width: 12rem;
			flex-direction: column;
			padding: var(--space-2xs);
			background: var(--bg-surface);
			border: 1px solid var(--rule-strong);
			border-radius: 6px;
		}

		.more-menu.open {
			display: flex;
		}

		.menu-item {
			order: 0;
			width: 100%;
			justify-content: flex-start;
			min-height: 44px;
			padding-inline: var(--space-sm);
			border: none;
			white-space: nowrap;
		}

		.menu-item:hover:not(:disabled) {
			background: var(--bg-subtle);
		}

		.btn-ghost-danger.menu-item {
			width: 100%;
			height: auto;
			gap: var(--space-xs);
			color: var(--status-danger);
			font-family: var(--font-display);
			font-size: var(--text-sm);
			font-weight: 600;
		}

		.menu-label {
			display: inline;
		}
	}
</style>
