<script lang="ts">
	import { onMount } from 'svelte';
	import type { HopVarietyResponse } from '$lib/api';
	import { fetchHopVarieties, fetchHopOrigins } from '$lib/api';
	import { calculateIBU_Tinseth, calculateTotalIBU, calculateBUGU, type Hop } from '$lib/brewing';
	import { EXTRACT_USE_ALLOWLIST, type HopUse, type HopForm, type RecipeHop } from './RecipeBuilder.svelte';

	// Hot-side (traditional pellet/whole) use values + display labels.
	const HOT_USE_OPTIONS: { value: HopUse; label: string }[] = [
		{ value: 'boil', label: 'Boil' },
		{ value: 'first_wort', label: 'First Wort' },
		{ value: 'whirlpool', label: 'Whirlpool' },
		{ value: 'dry_hop', label: 'Dry Hop' },
		{ value: 'mash', label: 'Mash' },
	];

	// Cold-side use values for Abstrax-Quantum-style extracts. Mirrors
	// the backend allowlist (EXTRACT_USE_ALLOWLIST). Long-form keys
	// (add_to_fermentation / add_to_package) are preserved verbatim
	// because the backend persists them that way for extracts.
	const EXTRACT_USE_OPTIONS: { value: HopUse; label: string }[] = [
		{ value: 'dry_hop', label: 'Dry Hop' },
		{ value: 'add_to_fermentation', label: 'Add to Fermentation' },
		{ value: 'add_to_package', label: 'Add to Package' },
		{ value: 'package', label: 'Package' },
		{ value: 'keg', label: 'Keg' },
		{ value: 'brite', label: 'Brite Tank' },
	];

	const EXTRACT_USE_SET = new Set<string>(EXTRACT_USE_ALLOWLIST);

	const HOT_DEFAULT_USE: HopUse = 'boil';
	const EXTRACT_DEFAULT_USE: HopUse = 'dry_hop';

	interface Props {
		hops: RecipeHop[];
		og?: number;
		batchSizeLiters?: number;
		onUpdate: (hops: RecipeHop[]) => void;
	}

	let { hops, og = 1.050, batchSizeLiters = 20, onUpdate }: Props = $props();

	let library = $state<HopVarietyResponse[]>([]);
	let origins = $state<string[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');
	let originFilter = $state('');
	let purposeFilter = $state('');
	let showBrowser = $state(false);

	// Editor-level mode toggle. When set to `extract`, the "+ Add Hop"
	// flow creates Abstrax-Quantum-style extracts (mL dosing, cold-side
	// use allowlist). Defaults to `hop` so existing behaviour is
	// preserved for non-extract users.
	let editorMode = $state<'hop' | 'extract'>('hop');

	// Calculate total IBU from current hops. Extracts contribute no
	// alpha-acid-derived IBU (cold-side, by-volume dosing), so they're
	// excluded from the Tinseth calculation entirely.
	let totalIBU = $derived(() => {
		if (hops.length === 0) return 0;

		const calcHops: Hop[] = hops
			.filter((h) => !h.is_extract)
			.map((h) => ({
				name: h.name,
				amount_grams: h.amount_grams,
				alpha_acid_percent: h.alpha_acid_percent,
				boil_time_minutes: h.boil_time_minutes,
				form: h.form,
				// `use` may carry an extract-only value on a stale row;
				// the filter above guarantees we won't pass one through.
				use: h.use as Hop['use']
			}));

		return calculateTotalIBU(calcHops, og, batchSizeLiters);
	});

	// Calculate BU:GU ratio
	let buguRatio = $derived(() => {
		return calculateBUGU(totalIBU(), og);
	});

	// Describe bitterness balance
	let bitterDescription = $derived(() => {
		const ratio = buguRatio();
		if (ratio < 0.3) return 'Very Sweet';
		if (ratio < 0.5) return 'Malty';
		if (ratio < 0.7) return 'Balanced';
		if (ratio < 0.9) return 'Hoppy';
		return 'Very Bitter';
	});

	// Calculate individual IBU contribution. Extract hops are cold-side
	// and contribute no IBU via Tinseth.
	function getHopIBU(hop: RecipeHop): number {
		if (hop.is_extract) return 0;
		const calcHop: Hop = {
			name: hop.name,
			amount_grams: hop.amount_grams,
			alpha_acid_percent: hop.alpha_acid_percent,
			boil_time_minutes: hop.boil_time_minutes,
			form: hop.form,
			use: hop.use as Hop['use']
		};
		return calculateIBU_Tinseth(calcHop, og, batchSizeLiters);
	}

	// Filter library based on search and filters
	let filteredLibrary = $derived(() => {
		return library.filter((h) => {
			const matchesSearch =
				!searchQuery ||
				h.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				h.origin?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				h.aroma_profile?.toLowerCase().includes(searchQuery.toLowerCase());

			const matchesOrigin = !originFilter || h.origin === originFilter;
			const matchesPurpose = !purposeFilter || h.purpose === purposeFilter;

			return matchesSearch && matchesOrigin && matchesPurpose;
		});
	});

	// Group library by purpose
	let groupedLibrary = $derived(() => {
		const groups: Record<string, HopVarietyResponse[]> = {};
		for (const hop of filteredLibrary()) {
			const purpose = hop.purpose || 'Other';
			if (!groups[purpose]) {
				groups[purpose] = [];
			}
			groups[purpose].push(hop);
		}
		// Sort groups: dual first, then bittering, then aroma
		const order = ['dual', 'bittering', 'aroma'];
		return Object.fromEntries(
			Object.entries(groups).sort(([a], [b]) => {
				const aIdx = order.indexOf(a.toLowerCase());
				const bIdx = order.indexOf(b.toLowerCase());
				if (aIdx >= 0 && bIdx >= 0) return aIdx - bIdx;
				if (aIdx >= 0) return -1;
				if (bIdx >= 0) return 1;
				return a.localeCompare(b);
			})
		);
	});

	// Group hops by use for display
	let groupedHops = $derived(() => {
		const groups: Record<string, RecipeHop[]> = {};
		for (const hop of hops) {
			const use = hop.use || 'boil';
			if (!groups[use]) {
				groups[use] = [];
			}
			groups[use].push(hop);
		}
		// Sort boil hops by time (longest first)
		if (groups.boil) {
			groups.boil.sort((a, b) => b.boil_time_minutes - a.boil_time_minutes);
		}
		return groups;
	});

	onMount(async () => {
		try {
			const [hopData, originsData] = await Promise.all([fetchHopVarieties(), fetchHopOrigins()]);
			library = hopData;
			origins = originsData.origins || [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load hops';
			console.error('Failed to load hops:', e);
		} finally {
			loading = false;
		}
	});

	function addHop(hop: HopVarietyResponse) {
		// Use average of alpha acid range, or default to 10%
		const avgAA =
			hop.alpha_acid_low && hop.alpha_acid_high
				? (hop.alpha_acid_low + hop.alpha_acid_high) / 2
				: hop.alpha_acid_low || hop.alpha_acid_high || 10;

		// `editorMode` chooses whether picked varieties enter as
		// traditional pellet hops or as Abstrax-Quantum-style extracts.
		// Quantum SKUs reuse real hop variety names (MOS=Mosaic,
		// CIT=Citra), so the same picker works for both modes — only
		// the dosing units / use allowlist differ.
		const isExtract = editorMode === 'extract';
		const newHop: RecipeHop = {
			...hop,
			amount_grams: isExtract ? 0 : 30,
			boil_time_minutes: isExtract ? 0 : 60,
			use: isExtract ? EXTRACT_DEFAULT_USE : HOT_DEFAULT_USE,
			form: 'pellet',
			alpha_acid_percent: isExtract ? 0 : avgAA,
			is_extract: isExtract,
			amount_ml: isExtract ? 1 : null,
		};
		onUpdate([...hops, newHop]);
		// Keep browser open to allow adding multiple items
	}

	function removeHop(index: number) {
		const updated = [...hops];
		updated.splice(index, 1);
		onUpdate(updated);
	}

	function updateHop(index: number, field: keyof RecipeHop, value: number | string | null) {
		const updated = hops.map((hop, i) => {
			if (i !== index) return hop;
			const next = { ...hop, [field]: value } as RecipeHop;
			// boil_time_minutes is overloaded across use classes (boil min /
			// stand min / dry-hop minutes-as-days*24*60). Resetting on every
			// use change keeps a stale duration from one class bleeding into
			// another (e.g. dry-hop's 5760 min surviving a switch back to
			// boil and inflating IBU). Extracts have no boil time, so
			// the reset is a no-op for them.
			if (field === 'use' && value !== hop.use && !hop.is_extract) {
				const useDefaults: Partial<Record<HopUse, number>> = {
					boil: 60,
					whirlpool: 0,
					dry_hop: 4 * 24 * 60,
					first_wort: 60,
					mash: 60,
				};
				next.boil_time_minutes = useDefaults[value as HopUse] ?? 0;
			}
			return next;
		});
		onUpdate(updated);
	}

	/**
	 * Flip a hop row between traditional Hop mode and Extract mode.
	 * Mode-specific fields are reset on flip so they don't leak
	 * across modes (a stale 60-min boil time on an extract, or a
	 * stale amount_ml on a pellet hop). Name is preserved. `use`
	 * is preserved iff it's valid in the new mode; otherwise it
	 * falls back to the mode's default (boil / dry_hop).
	 */
	function toggleHopMode(index: number, toExtract: boolean) {
		const updated = hops.map((hop, i) => {
			if (i !== index) return hop;
			if (Boolean(hop.is_extract) === toExtract) return hop;

			const next: RecipeHop = { ...hop, is_extract: toExtract };
			if (toExtract) {
				// Switching into Extract: clear alpha + grams + boil-time,
				// seed a default mL value, restrict use to the cold-side
				// allowlist.
				next.alpha_acid_percent = 0;
				next.amount_grams = 0;
				next.boil_time_minutes = 0;
				next.amount_ml = 1;
				next.use = EXTRACT_USE_SET.has(hop.use)
					? hop.use
					: EXTRACT_DEFAULT_USE;
			} else {
				// Switching back to Hop: clear amount_ml, restore a
				// sensible default grams + boil-time + AA so the row
				// is immediately editable.
				next.amount_ml = null;
				next.amount_grams = hop.amount_grams || 30;
				next.boil_time_minutes = 60;
				next.alpha_acid_percent = hop.alpha_acid_percent || 10;
				// Cold-side-only use values (add_to_package, package,
				// keg, brite, add_to_fermentation) aren't valid in the
				// hot-side editor — collapse them to boil. `dry_hop`
				// is valid in both modes so it survives.
				const validHotUses = new Set<HopUse>([
					'boil',
					'whirlpool',
					'dry_hop',
					'first_wort',
					'mash',
				]);
				next.use = validHotUses.has(hop.use)
					? hop.use
					: HOT_DEFAULT_USE;
			}
			return next;
		});
		onUpdate(updated);
	}

	function formatAlphaRange(low?: number, high?: number): string {
		if (low != null && high != null) return `${low.toFixed(1)}-${high.toFixed(1)}%`;
		if (low != null) return `${low.toFixed(1)}%+`;
		if (high != null) return `≤${high.toFixed(1)}%`;
		return '--';
	}

	function formatUse(use: HopUse): string {
		const labels: Record<HopUse, string> = {
			boil: 'Boil',
			whirlpool: 'Whirlpool',
			dry_hop: 'Dry Hop',
			first_wort: 'First Wort',
			mash: 'Mash',
			add_to_fermentation: 'Add to Fermentation',
			add_to_package: 'Add to Package',
			package: 'Package',
			keg: 'Keg',
			brite: 'Brite Tank',
		};
		return labels[use] || use;
	}

	function getPurposeColor(purpose?: string): string {
		switch (purpose?.toLowerCase()) {
			case 'bittering':
				return 'var(--warning)';
			case 'aroma':
				return 'var(--positive)';
			case 'dual':
				return 'var(--info)';
			default:
				return 'var(--text-tertiary)';
		}
	}
</script>

<div class="hop-selector">
	<div class="selector-header">
		<div class="header-left">
			<h3>
				<span class="header-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
						<circle cx="12" cy="5" r="3" fill="currentColor" opacity="0.7" />
						<circle cx="8" cy="10" r="3" fill="currentColor" opacity="0.65" />
						<circle cx="16" cy="10" r="3" fill="currentColor" opacity="0.6" />
						<circle cx="12" cy="15" r="3" fill="currentColor" opacity="0.55" />
						<path d="M12 18v3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
					</svg>
				</span>
				Hop Schedule
			</h3>
			{#if hops.length > 0}
				<span class="stats">
					{totalIBU().toFixed(0)} IBU · BU:GU {buguRatio().toFixed(2)} ·
					<span class="balance">{bitterDescription()}</span>
				</span>
			{/if}
		</div>
		<div class="header-right">
			<div
				class="mode-toggle"
				role="radiogroup"
				aria-label="Hop addition type"
			>
				<button
					type="button"
					class="mode-btn"
					class:active={editorMode === 'hop'}
					role="radio"
					aria-checked={editorMode === 'hop'}
					onclick={() => (editorMode = 'hop')}
				>
					Hop
				</button>
				<button
					type="button"
					class="mode-btn"
					class:active={editorMode === 'extract'}
					role="radio"
					aria-checked={editorMode === 'extract'}
					onclick={() => (editorMode = 'extract')}
				>
					Extract
				</button>
			</div>
			<button type="button" class="add-btn" onclick={() => (showBrowser = true)}> + Add Hop </button>
		</div>
	</div>

	{#if hops.length === 0}
		<div class="empty-state">
			<p>No hops added yet.</p>
		</div>
	{:else}
		<div class="hops-list">
			{#each Object.entries(groupedHops()) as [use, hopGroup]}
				<div class="use-group">
					<h4 class="use-name">{formatUse(use as HopUse)}</h4>
					{#each hopGroup as hop, i (hop.id + '-' + i)}
						{@const hopIndex = hops.indexOf(hop)}
						{@const hopIBU = getHopIBU(hop)}
						<div class="hop-item">
							<div class="hop-main">
								<div class="hop-info">
									<span class="hop-name">{hop.name}</span>
									{#if hop.origin}
										<span class="hop-origin">{hop.origin}</span>
									{/if}
								</div>
								<div class="hop-ibu">
									{#if hopIBU > 0}
										<span class="ibu-value">+{hopIBU.toFixed(0)} IBU</span>
									{:else}
										<span class="ibu-zero">0 IBU</span>
									{/if}
								</div>
							</div>
							<div class="hop-controls">
								<div class="control-row">
									<div class="control-group mode-control-group">
										<label id="hop-mode-label-{hopIndex}">Type</label>
										<div
											class="mode-toggle mode-toggle-row"
											role="radiogroup"
											aria-labelledby="hop-mode-label-{hopIndex}"
										>
											<button
												type="button"
												class="mode-btn"
												class:active={!hop.is_extract}
												role="radio"
												aria-checked={!hop.is_extract}
												onclick={() => toggleHopMode(hopIndex, false)}
											>
												Hop
											</button>
											<button
												type="button"
												class="mode-btn"
												class:active={Boolean(hop.is_extract)}
												role="radio"
												aria-checked={Boolean(hop.is_extract)}
												onclick={() => toggleHopMode(hopIndex, true)}
											>
												Extract
											</button>
										</div>
									</div>

									{#if hop.is_extract}
										<div class="control-group">
											<label for="hop-ml-{hopIndex}">Amount</label>
											<div class="input-with-unit">
												<input
													id="hop-ml-{hopIndex}"
													type="number"
													step="0.1"
													min="0.1"
													value={hop.amount_ml ?? 1}
													onchange={(e) =>
														updateHop(
															hopIndex,
															'amount_ml',
															parseFloat(e.currentTarget.value) || 0,
														)}
												/>
												<span class="unit">mL</span>
											</div>
											<small class="ml-helper">1 mL ≈ 28 g pellet equivalent</small>
										</div>
									{:else}
										<div class="control-group">
											<label for="hop-amount-{hopIndex}">Amount</label>
											<div class="input-with-unit">
												<input
													id="hop-amount-{hopIndex}"
													type="number"
													step="5"
													min="0"
													value={hop.amount_grams}
													onchange={(e) =>
														updateHop(hopIndex, 'amount_grams', parseFloat(e.currentTarget.value) || 0)}
												/>
												<span class="unit">g</span>
											</div>
										</div>

										<div class="control-group">
											<label for="hop-aa-{hopIndex}">AA%</label>
											<input
												id="hop-aa-{hopIndex}"
												type="number"
												step="0.1"
												min="0"
												max="25"
												class="aa-input"
												value={hop.alpha_acid_percent}
												onchange={(e) =>
													updateHop(
														hopIndex,
														'alpha_acid_percent',
														parseFloat(e.currentTarget.value) || 0
													)}
											/>
										</div>

										{#if hop.use === 'boil' || hop.use === 'whirlpool'}
											<div class="control-group">
												<label for="hop-time-{hopIndex}"
													>{hop.use === 'whirlpool' ? 'Stand' : 'Time'}</label
												>
												<div class="input-with-unit">
													<input
														id="hop-time-{hopIndex}"
														type="number"
														step="5"
														min="0"
														max={hop.use === 'whirlpool' ? 60 : 90}
														value={hop.boil_time_minutes}
														onchange={(e) =>
															updateHop(
																hopIndex,
																'boil_time_minutes',
																parseInt(e.currentTarget.value) || 0
															)}
													/>
													<span class="unit">min</span>
												</div>
											</div>
										{/if}
									{/if}

									<div class="control-group">
										<label for="hop-use-{hopIndex}">Use</label>
										<select
											id="hop-use-{hopIndex}"
											value={hop.use}
											onchange={(e) =>
												updateHop(hopIndex, 'use', e.currentTarget.value as HopUse)}
										>
											{#if hop.is_extract}
												{#each EXTRACT_USE_OPTIONS as opt (opt.value)}
													<option value={opt.value}>{opt.label}</option>
												{/each}
											{:else}
												{#each HOT_USE_OPTIONS as opt (opt.value)}
													<option value={opt.value}>{opt.label}</option>
												{/each}
											{/if}
										</select>
									</div>

									{#if !hop.is_extract}
										<div class="control-group">
											<label for="hop-form-{hopIndex}">Form</label>
											<select
												id="hop-form-{hopIndex}"
												value={hop.form}
												onchange={(e) =>
													updateHop(hopIndex, 'form', e.currentTarget.value as HopForm)}
											>
												<option value="pellet">Pellet</option>
												<option value="whole">Whole</option>
												<option value="plug">Plug</option>
											</select>
										</div>
									{/if}
								</div>

								<button type="button" class="remove-btn" onclick={() => removeHop(hopIndex)}>
									×
								</button>
							</div>
						</div>
					{/each}
				</div>
			{/each}
		</div>
	{/if}

	{#if showBrowser}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div class="browser-overlay" onclick={() => (showBrowser = false)} role="presentation">
			<div class="browser-modal" role="dialog" aria-modal="true" aria-labelledby="hop-browser-title" tabindex="-1" onclick={(e) => e.stopPropagation()}>
				<div class="browser-header">
					<h4 id="hop-browser-title">
						{editorMode === 'extract' ? 'Add Hop Extract' : 'Add Hop'}
					</h4>
					<button type="button" class="close-btn" onclick={() => (showBrowser = false)}>×</button>
				</div>
				{#if editorMode === 'extract'}
					<p class="extract-hint">
						Pick the variety the extract was made from — Abstrax Quantum SKUs follow real hop varieties (MOS=Mosaic, CIT=Citra).
					</p>
				{/if}

				{#if loading}
					<div class="loading">
						<div class="spinner"></div>
						<p>Loading hops...</p>
					</div>
				{:else if error}
					<div class="error-box">
						<p class="error-text">{error}</p>
					</div>
				{:else}
					<div class="filters">
						<input
							type="text"
							placeholder="Search hops..."
							bind:value={searchQuery}
							class="search-input"
						/>
						<div class="filter-row">
							<select bind:value={purposeFilter} class="filter-select">
								<option value="">All Purposes</option>
								<option value="bittering">Bittering</option>
								<option value="aroma">Aroma</option>
								<option value="dual">Dual Purpose</option>
							</select>
							<select bind:value={originFilter} class="filter-select">
								<option value="">All Origins</option>
								{#each origins as origin}
									<option value={origin}>{origin}</option>
								{/each}
							</select>
						</div>
					</div>

					<div class="library-list">
						{#each Object.entries(groupedLibrary()) as [purpose, hopGroup] (purpose)}
							<div class="purpose-group">
								<h5 class="purpose-name" style="color: {getPurposeColor(purpose)}">{purpose}</h5>
								{#each hopGroup as hop (hop.id)}
									<button type="button" class="library-item" onclick={() => addHop(hop)}>
										<div class="item-main">
											<span class="item-name">{hop.name}</span>
											{#if hop.origin}
												<span class="item-origin">{hop.origin}</span>
											{/if}
										</div>
										<div class="item-details">
											<span class="item-aa">
												{formatAlphaRange(hop.alpha_acid_low, hop.alpha_acid_high)}
											</span>
											{#if hop.aroma_profile}
												<span class="item-aroma">{hop.aroma_profile}</span>
											{/if}
										</div>
									</button>
								{/each}
							</div>
						{/each}
						{#if Object.keys(groupedLibrary()).length === 0}
							<div class="no-results">
								<p>No hops match your filters</p>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.hop-selector {
		--section-accent: var(--positive);
		--section-accent-strong: rgba(34, 197, 94, 0.35);
		--section-accent-soft: rgba(34, 197, 94, 0.18);
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.selector-header {
		position: relative;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-4) var(--space-4);
		background: var(--bg-elevated);
		background-image:
			linear-gradient(120deg, var(--section-accent-soft), rgba(24, 24, 27, 0) 70%),
			var(--recipe-grain-texture);
		background-size: cover, 8px 8px;
		border: 1px solid var(--border-subtle);
		border-radius: 10px;
		overflow: hidden;
	}

	.selector-header::after {
		content: '';
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		height: 2px;
		background: linear-gradient(90deg, var(--section-accent), transparent);
		opacity: 0.7;
	}

	.selector-header > * {
		position: relative;
		z-index: 1;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.mode-toggle {
		display: inline-flex;
		align-items: stretch;
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		overflow: hidden;
	}

	.mode-toggle.mode-toggle-row {
		align-self: flex-start;
	}

	.mode-btn {
		padding: var(--space-1) var(--space-3);
		background: transparent;
		color: var(--text-secondary);
		border: none;
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		transition: background var(--transition), color var(--transition);
	}

	.mode-btn + .mode-btn {
		border-left: 1px solid var(--border-default);
	}

	.mode-btn:hover {
		color: var(--text-primary);
		background: var(--bg-hover);
	}

	.mode-btn.active {
		background: var(--section-accent);
		color: white;
	}

	.mode-control-group {
		min-width: 110px;
	}

	.ml-helper {
		font-size: 10px;
		color: var(--text-tertiary);
		margin-top: var(--space-1);
		line-height: 1.2;
	}

	.extract-hint {
		font-size: 12px;
		color: var(--text-secondary);
		padding: var(--space-2) var(--space-4) 0;
		margin: 0;
		line-height: 1.4;
	}

	h3 {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.header-icon {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		border-radius: 6px;
		background: rgba(34, 197, 94, 0.18);
		color: var(--section-accent);
	}

	.header-icon svg {
		width: 16px;
		height: 16px;
	}

	.stats {
		font-size: 13px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.balance {
		color: var(--positive);
	}

	.add-btn {
		padding: var(--space-2) var(--space-3);
		background: var(--section-accent);
		color: white;
		border: none;
		border-radius: 6px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		box-shadow: 0 6px 12px rgba(0, 0, 0, 0.3);
		transition: background var(--transition), transform var(--transition), box-shadow var(--transition);
	}

	.add-btn:hover {
		filter: brightness(1.05);
		transform: translateY(-1px);
		box-shadow: 0 10px 16px rgba(0, 0, 0, 0.35);
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-6);
		background: var(--bg-surface);
		border: 1px dashed var(--section-accent-strong);
		border-radius: 8px;
	}

	.empty-state p {
		color: var(--text-secondary);
		margin: 0;
	}

	.hops-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.use-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.use-name {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0;
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	.hop-item {
		position: relative;
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		transition: border-color var(--transition), transform var(--transition), box-shadow var(--transition);
		overflow: hidden;
	}

	.hop-item::before {
		content: '';
		position: absolute;
		inset: 0 auto 0 0;
		width: 3px;
		background: var(--section-accent);
		opacity: 0.35;
	}

	.hop-item:hover {
		border-color: var(--section-accent);
		transform: translateY(-1px);
		box-shadow: 0 10px 20px rgba(0, 0, 0, 0.35);
	}

	.hop-main {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
	}

	.hop-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.hop-name {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.hop-origin {
		font-size: 12px;
		color: var(--text-tertiary);
	}

	.hop-ibu {
		text-align: right;
	}

	.ibu-value {
		font-size: 14px;
		font-weight: 600;
		color: var(--positive);
		font-family: var(--font-mono);
	}

	.ibu-zero {
		font-size: 14px;
		color: var(--text-tertiary);
		font-family: var(--font-mono);
	}

	.hop-controls {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		gap: var(--space-3);
	}

	.control-row {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
	}

	.control-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.control-group label {
		font-size: 10px;
		font-weight: 500;
		color: var(--text-tertiary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.input-with-unit {
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.input-with-unit input {
		width: 60px;
		padding: var(--space-2);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
		font-family: var(--font-mono);
		text-align: right;
	}

	.aa-input {
		width: 50px;
		padding: var(--space-2);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
		font-family: var(--font-mono);
		text-align: right;
	}

	.input-with-unit input:focus,
	.aa-input:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	.unit {
		font-size: 11px;
		color: var(--text-secondary);
	}

	.control-group select {
		padding: var(--space-2);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 12px;
		min-width: 80px;
	}

	.control-group select:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	.remove-btn {
		width: 24px;
		height: 24px;
		padding: 0;
		background: transparent;
		color: var(--text-tertiary);
		border: none;
		border-radius: 4px;
		font-size: 18px;
		cursor: pointer;
		transition: all var(--transition);
		flex-shrink: 0;
	}

	.remove-btn:hover {
		background: var(--negative);
		color: white;
	}

	/* Browser Modal */
	.browser-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
	}

	.browser-modal {
		width: 90%;
		max-width: 600px;
		max-height: 80vh;
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 8px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.browser-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
	}

	.browser-header h4 {
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.close-btn {
		width: 28px;
		height: 28px;
		padding: 0;
		background: transparent;
		color: var(--text-secondary);
		border: none;
		border-radius: 4px;
		font-size: 20px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.close-btn:hover {
		background: var(--bg-hover);
		color: var(--text-primary);
	}

	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-6);
	}

	.spinner {
		width: 24px;
		height: 24px;
		border: 2px solid var(--gray-700);
		border-top-color: var(--accent-primary);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}

	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}

	.error-box {
		padding: var(--space-4);
		margin: var(--space-4);
		background: rgba(239, 68, 68, 0.1);
		border: 1px solid var(--negative);
		border-radius: 6px;
	}

	.error-text {
		font-size: 14px;
		color: var(--negative);
		margin: 0;
		text-align: center;
	}

	.filters {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
		padding: var(--space-4);
		border-bottom: 1px solid var(--border-subtle);
	}

	.search-input {
		width: 100%;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
	}

	.search-input:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	.filter-row {
		display: flex;
		gap: var(--space-2);
	}

	.filter-select {
		flex: 1;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 13px;
	}

	.filter-select:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	.library-list {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-4);
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.purpose-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.purpose-name {
		font-size: 12px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0;
		padding: var(--space-1) 0;
		border-bottom: 1px solid var(--border-subtle);
	}

	.library-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		text-align: left;
		cursor: pointer;
		transition: all var(--transition);
	}

	.library-item:hover {
		border-color: var(--section-accent);
		background: var(--bg-hover);
		box-shadow: inset 0 0 0 1px var(--section-accent-soft);
	}

	.item-main {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.item-name {
		font-size: 14px;
		color: var(--text-primary);
	}

	.item-origin {
		font-size: 12px;
		color: var(--text-tertiary);
	}

	.item-details {
		display: flex;
		flex-direction: column;
		align-items: flex-end;
		gap: var(--space-1);
	}

	.item-aa {
		font-size: 12px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.item-aroma {
		font-size: 11px;
		color: var(--text-tertiary);
		max-width: 150px;
		text-align: right;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}

	.no-results {
		display: flex;
		justify-content: center;
		padding: var(--space-6);
	}

	.no-results p {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	/* Responsive */
	@media (max-width: 640px) {
		.control-row {
			flex-direction: column;
			width: 100%;
		}

		.control-group {
			flex-direction: row;
			align-items: center;
			justify-content: space-between;
			width: 100%;
		}

		.control-group select,
		.input-with-unit input,
		.aa-input {
			width: auto;
			flex: 1;
			max-width: 100px;
		}
	}
</style>
