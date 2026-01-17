<script lang="ts">
	import { onMount } from 'svelte';
	import type { HopVarietyResponse } from '$lib/api';
	import { fetchHopVarieties, fetchHopOrigins } from '$lib/api';
	import { calculateIBU_Tinseth, calculateTotalIBU, calculateBUGU, type Hop } from '$lib/brewing';

	type HopUse = 'boil' | 'whirlpool' | 'dry_hop' | 'first_wort' | 'mash';
	type HopForm = 'pellet' | 'whole' | 'plug';

	interface RecipeHop extends HopVarietyResponse {
		amount_grams: number;
		boil_time_minutes: number;
		use: HopUse;
		form: HopForm;
		alpha_acid_percent: number; // Selected AA% within range
	}

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

	// Calculate total IBU from current hops
	let totalIBU = $derived(() => {
		if (hops.length === 0) return 0;

		const calcHops: Hop[] = hops.map((h) => ({
			name: h.name,
			amount_grams: h.amount_grams,
			alpha_acid_percent: h.alpha_acid_percent,
			boil_time_minutes: h.boil_time_minutes,
			form: h.form,
			use: h.use
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

	// Calculate individual IBU contribution
	function getHopIBU(hop: RecipeHop): number {
		const calcHop: Hop = {
			name: hop.name,
			amount_grams: hop.amount_grams,
			alpha_acid_percent: hop.alpha_acid_percent,
			boil_time_minutes: hop.boil_time_minutes,
			form: hop.form,
			use: hop.use
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

		const newHop: RecipeHop = {
			...hop,
			amount_grams: 30, // Default amount
			boil_time_minutes: 60, // Default boil time
			use: 'boil',
			form: 'pellet',
			alpha_acid_percent: avgAA
		};
		onUpdate([...hops, newHop]);
		showBrowser = false;
	}

	function removeHop(index: number) {
		const updated = [...hops];
		updated.splice(index, 1);
		onUpdate(updated);
	}

	function updateHop(index: number, field: keyof RecipeHop, value: number | string) {
		const updated = hops.map((hop, i) => (i === index ? { ...hop, [field]: value } : hop));
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
			mash: 'Mash'
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
			<h3>Hop Schedule</h3>
			{#if hops.length > 0}
				<span class="stats">
					{totalIBU().toFixed(0)} IBU · BU:GU {buguRatio().toFixed(2)} ·
					<span class="balance">{bitterDescription()}</span>
				</span>
			{/if}
		</div>
		<button type="button" class="add-btn" onclick={() => (showBrowser = true)}> + Add Hop </button>
	</div>

	{#if hops.length === 0}
		<div class="empty-state">
			<p>No hops added yet.</p>
			<button type="button" class="browse-btn" onclick={() => (showBrowser = true)}>
				Browse Library
			</button>
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
									<div class="control-group">
										<label>Amount</label>
										<div class="input-with-unit">
											<input
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
										<label>AA%</label>
										<input
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

									{#if hop.use === 'boil'}
										<div class="control-group">
											<label>Time</label>
											<div class="input-with-unit">
												<input
													type="number"
													step="5"
													min="0"
													max="90"
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

									<div class="control-group">
										<label>Use</label>
										<select
											value={hop.use}
											onchange={(e) =>
												updateHop(hopIndex, 'use', e.currentTarget.value as HopUse)}
										>
											<option value="boil">Boil</option>
											<option value="first_wort">First Wort</option>
											<option value="whirlpool">Whirlpool</option>
											<option value="dry_hop">Dry Hop</option>
											<option value="mash">Mash</option>
										</select>
									</div>

									<div class="control-group">
										<label>Form</label>
										<select
											value={hop.form}
											onchange={(e) =>
												updateHop(hopIndex, 'form', e.currentTarget.value as HopForm)}
										>
											<option value="pellet">Pellet</option>
											<option value="whole">Whole</option>
											<option value="plug">Plug</option>
										</select>
									</div>
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
		<div class="browser-overlay" onclick={() => (showBrowser = false)}>
			<div class="browser-modal" onclick={(e) => e.stopPropagation()}>
				<div class="browser-header">
					<h4>Add Hop</h4>
					<button type="button" class="close-btn" onclick={() => (showBrowser = false)}>×</button>
				</div>

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
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-3) var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	h3 {
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
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
		background: var(--accent-primary);
		color: var(--bg-surface);
		border: none;
		border-radius: 4px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background var(--transition);
	}

	.add-btn:hover {
		background: var(--accent-secondary);
	}

	.empty-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-3);
		padding: var(--space-6);
		background: var(--bg-surface);
		border: 1px dashed var(--border-default);
		border-radius: 6px;
	}

	.empty-state p {
		color: var(--text-secondary);
		margin: 0;
	}

	.browse-btn {
		padding: var(--space-2) var(--space-4);
		background: transparent;
		color: var(--accent-primary);
		border: 1px solid var(--accent-primary);
		border-radius: 4px;
		font-size: 13px;
		cursor: pointer;
		transition: all var(--transition);
	}

	.browse-btn:hover {
		background: var(--accent-primary);
		color: var(--bg-surface);
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
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		padding: var(--space-3) var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		transition: border-color var(--transition);
	}

	.hop-item:hover {
		border-color: var(--border-default);
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
		border-radius: 4px;
		text-align: left;
		cursor: pointer;
		transition: all var(--transition);
	}

	.library-item:hover {
		border-color: var(--accent-primary);
		background: var(--bg-hover);
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
