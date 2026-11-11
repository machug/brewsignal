<script lang="ts">
	import { onMount } from 'svelte';
	import type { FermentableResponse } from '$lib/api';
	import { fetchFermentables, fetchFermentableTypes, fetchFermentableOrigins } from '$lib/api';
	import { calculateOG, calculateSRM, srmToHex, type Fermentable } from '$lib/brewing';

	interface RecipeFermentable extends FermentableResponse {
		amount_kg: number;
	}

	interface Props {
		fermentables: RecipeFermentable[];
		batchSizeLiters?: number;
		efficiencyPercent?: number;
		onUpdate: (fermentables: RecipeFermentable[]) => void;
	}

	let { fermentables, batchSizeLiters = 20, efficiencyPercent = 72, onUpdate }: Props = $props();

	let library = $state<FermentableResponse[]>([]);
	let types = $state<string[]>([]);
	let origins = $state<string[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');
	let typeFilter = $state('');
	let originFilter = $state('');
	let showBrowser = $state(false);

	// Calculate totals
	let totalKg = $derived(fermentables.reduce((sum, f) => sum + f.amount_kg, 0));

	// Calculate recipe stats from current fermentables
	let recipeStats = $derived(() => {
		if (fermentables.length === 0) {
			return { og: 1.000, srm: 0, color_hex: '#FFE699' };
		}

		// Convert to calculation format
		const calcFermentables: Fermentable[] = fermentables.map(f => ({
			name: f.name,
			amount_kg: f.amount_kg,
			potential_sg: f.potential_sg || 1.036,
			color_srm: f.color_srm || 2,
			type: f.type ?? undefined
		}));

		const batch = {
			batch_size_liters: batchSizeLiters,
			efficiency_percent: efficiencyPercent,
			boil_time_minutes: 60
		};

		const og = calculateOG(calcFermentables, batch);
		const srm = calculateSRM(calcFermentables, batchSizeLiters);
		const color_hex = srmToHex(srm);

		return { og, srm, color_hex };
	});

	// Filter library based on search and filters
	let filteredLibrary = $derived(() => {
		return library.filter((f) => {
			const matchesSearch =
				!searchQuery ||
				f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				f.maltster?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				f.origin?.toLowerCase().includes(searchQuery.toLowerCase());

			const matchesType = !typeFilter || f.type === typeFilter;
			const matchesOrigin = !originFilter || f.origin === originFilter;

			return matchesSearch && matchesType && matchesOrigin;
		});
	});

	// Group library by type
	let groupedLibrary = $derived(() => {
		const groups: Record<string, FermentableResponse[]> = {};
		for (const ferm of filteredLibrary()) {
			const type = ferm.type || 'Other';
			if (!groups[type]) {
				groups[type] = [];
			}
			groups[type].push(ferm);
		}
		// Sort groups: base first, then alphabetically
		const order = ['base', 'specialty', 'adjunct', 'sugar', 'extract', 'fruit', 'other'];
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

	onMount(async () => {
		try {
			const [fermData, typesData, originsData] = await Promise.all([
				fetchFermentables(),
				fetchFermentableTypes(),
				fetchFermentableOrigins()
			]);
			library = fermData;
			types = typesData.types || [];
			origins = originsData.origins || [];
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load fermentables';
			console.error('Failed to load fermentables:', e);
		} finally {
			loading = false;
		}
	});

	function addFermentable(ferm: FermentableResponse) {
		// Check if already added
		if (fermentables.some((f) => f.id === ferm.id)) {
			return;
		}

		const newFerm: RecipeFermentable = {
			...ferm,
			amount_kg: 0.5 // Default amount
		};
		onUpdate([...fermentables, newFerm]);
		// Keep browser open to allow adding multiple items
	}

	function removeFermentable(id: number) {
		onUpdate(fermentables.filter((f) => f.id !== id));
	}

	function updateAmount(id: number, amount: number) {
		onUpdate(
			fermentables.map((f) => (f.id === id ? { ...f, amount_kg: Math.max(0, amount) } : f))
		);
	}

	function getPercent(amount: number): string {
		if (!amount || !totalKg) return '0%';
		return ((amount / totalKg) * 100).toFixed(1) + '%';
	}

	function formatColor(srm?: number): string {
		if (srm === undefined || srm === null) return '--';
		return srm.toFixed(0) + '°L';
	}

	function formatPotential(sg?: number): string {
		if (sg === undefined || sg === null) return '--';
		return sg.toFixed(3);
	}

</script>

<div class="fermentable-selector">
	<div class="selector-header">
		<div class="header-left">
			<h3>
				Grain Bill
			</h3>
			{#if fermentables.length > 0}
				<span class="stats">
					{totalKg.toFixed(2)}&thinsp;kg · OG {recipeStats().og.toFixed(3)} ·
					<span class="color-swatch" style="background-color: {recipeStats().color_hex}"></span>
					{recipeStats().srm.toFixed(0)}&thinsp;SRM
				</span>
			{/if}
		</div>
		<button type="button" class="add-btn" onclick={() => (showBrowser = true)}>
			+ Add Fermentable
		</button>
	</div>

	{#if fermentables.length === 0}
		<div class="empty-state">
			<p>No fermentables added yet.</p>
		</div>
	{:else}
		<div class="fermentables-list">
			{#each fermentables as ferm (ferm.id)}
				<div class="ferm-item">
					<div class="ferm-main">
						<div class="ferm-info">
							<span class="ferm-name">{ferm.name}</span>
							{#if ferm.type}
								<span class="ferm-type">
									{ferm.type}
								</span>
							{/if}
						</div>
						<div class="ferm-details">
							{#if ferm.maltster}
								<span class="detail">{ferm.maltster}</span>
							{/if}
							{#if ferm.color_srm}
								<span class="detail">{formatColor(ferm.color_srm)}</span>
							{/if}
							{#if ferm.potential_sg}
								<span class="detail">{formatPotential(ferm.potential_sg)}</span>
							{/if}
						</div>
					</div>
					<div class="ferm-controls">
						<div class="amount-input">
							<input
								type="number"
								step="0.1"
								min="0"
								aria-label="Amount in kg for {ferm.name}"
								value={ferm.amount_kg}
								onchange={(e) => updateAmount(ferm.id, parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">kg</span>
						</div>
						<span class="percent">{getPercent(ferm.amount_kg)}</span>
						<button type="button" class="remove-btn" aria-label="Remove {ferm.name}" onclick={() => removeFermentable(ferm.id)}>
							×
						</button>
					</div>
				</div>
			{/each}
		</div>
	{/if}

	{#if showBrowser}
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div class="browser-overlay" onclick={() => (showBrowser = false)} role="presentation">
			<div class="browser-modal" role="dialog" aria-modal="true" aria-labelledby="fermentable-browser-title" tabindex="-1" onclick={(e) => e.stopPropagation()}>
				<div class="browser-header">
					<h4 id="fermentable-browser-title">Add Fermentable</h4>
					<button type="button" class="close-btn" aria-label="Close" onclick={() => (showBrowser = false)}>×</button>
				</div>

				{#if loading}
					<div class="loading">
						<div class="spinner"></div>
						<p>Loading fermentables...</p>
					</div>
				{:else if error}
					<div class="error-box">
						<p class="error-text">{error}</p>
					</div>
				{:else}
					<div class="filters">
						<input
							type="text"
							placeholder="Search fermentables..."
							bind:value={searchQuery}
							class="search-input"
						/>
						<div class="filter-row">
							<select bind:value={typeFilter} class="filter-select">
								<option value="">All Types</option>
								{#each types as type}
									<option value={type}>{type}</option>
								{/each}
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
						{#each Object.entries(groupedLibrary()) as [type, fermGroup] (type)}
							<div class="type-group">
								<h5 class="type-name">{type}</h5>
								{#each fermGroup as ferm (ferm.id)}
									{@const isAdded = fermentables.some((f) => f.id === ferm.id)}
									<button
										type="button"
										class="library-item"
										class:added={isAdded}
										disabled={isAdded}
										onclick={() => addFermentable(ferm)}
									>
										<div class="item-main">
											<span class="item-name">{ferm.name}</span>
											{#if ferm.maltster}
												<span class="item-maltster">{ferm.maltster}</span>
											{/if}
										</div>
										<div class="item-details">
											{#if ferm.color_srm}
												<span class="item-color">
													<span
														class="color-dot"
														style="background-color: {srmToHex(ferm.color_srm)}"
													></span>
													{ferm.color_srm.toFixed(0)}&thinsp;°L
												</span>
											{/if}
											{#if ferm.potential_sg}
												<span class="item-potential">{ferm.potential_sg.toFixed(3)}</span>
											{/if}
										</div>
									</button>
								{/each}
							</div>
						{/each}
						{#if Object.keys(groupedLibrary()).length === 0}
							<div class="no-results">
								<p>No fermentables match your filters</p>
							</div>
						{/if}
					</div>
				{/if}
			</div>
		</div>
	{/if}
</div>

<style>
	.fermentable-selector {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding-bottom: var(--space-xs);
		border-bottom: 1px solid var(--rule-strong);
	}

	.header-left {
		display: flex;
		align-items: baseline;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-md);
		min-width: 0;
	}

	h3 {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-secondary);
		margin: 0;
	}

	.stats {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-2xs);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.color-swatch {
		display: inline-block;
		width: 14px;
		height: 14px;
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
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

	.add-btn:focus-visible,
	.remove-btn:focus-visible,
	.close-btn:focus-visible,
	.library-item:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.empty-state {
		padding: var(--space-md);
		border: 1px dashed var(--rule-strong);
		border-radius: 4px;
	}

	.empty-state p {
		color: var(--ink-secondary);
		font-size: var(--text-sm);
		margin: 0;
	}

	/* Fields: 44px, 1px strong rule, visible accent focus ring */
	.amount-input input,
	.search-input,
	.filter-select {
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		box-sizing: border-box;
	}

	.search-input,
	.filter-select {
		font-family: var(--font-body);
	}

	.amount-input input:focus-visible,
	.search-input:focus-visible,
	.filter-select:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.amount-input {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.unit {
		font-size: var(--text-sm);
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

	/* Browser modal */
	.browser-overlay {
		position: fixed;
		inset: 0;
		background: color-mix(in oklch, var(--bg-canvas) 80%, transparent);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-md);
	}

	.browser-modal {
		width: 100%;
		max-width: 600px;
		max-height: 80vh;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 6px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.browser-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-sm) var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.browser-header h4 {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0;
	}

	.close-btn {
		width: 44px;
		height: 44px;
		margin: -8px -12px -8px 0;
		padding: 0;
		background: transparent;
		color: var(--ink-secondary);
		border: 1px solid transparent;
		border-radius: 4px;
		font-size: 22px;
		line-height: 1;
		cursor: pointer;
	}

	.close-btn:hover {
		border-color: var(--rule-strong);
		color: var(--ink-primary);
	}

	.loading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-lg);
		color: var(--ink-secondary);
		font-size: var(--text-sm);
	}

	.loading p {
		margin: 0;
	}

	.spinner {
		width: 24px;
		height: 24px;
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
		.spinner {
			animation-duration: 2.4s;
		}
	}

	.error-box {
		padding: var(--space-sm) var(--space-md);
		margin: var(--space-md);
		background: var(--bg-surface);
		border: 1px solid var(--status-danger);
		border-radius: 4px;
	}

	.error-text {
		font-size: var(--text-sm);
		color: var(--status-danger);
		margin: 0;
	}

	.filters {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		padding: var(--space-md);
		border-bottom: 1px solid var(--rule-hairline);
	}

	.search-input {
		width: 100%;
	}

	.filter-row {
		display: flex;
		gap: var(--space-xs);
	}

	.filter-select {
		flex: 1;
		min-width: 0;
	}

	.library-list {
		flex: 1;
		overflow-y: auto;
		padding: var(--space-md);
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
	}

	.library-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-sm);
		width: 100%;
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: transparent;
		border: none;
		border-bottom: 1px solid var(--rule-hairline);
		color: var(--ink-primary);
		font-family: inherit;
		text-align: left;
		cursor: pointer;
	}

	.library-item:hover:not(:disabled) {
		background: var(--bg-subtle);
	}

	.item-main {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}

	.item-name {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
	}

	.item-details {
		display: flex;
		gap: var(--space-sm);
		align-items: center;
		flex-shrink: 0;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}

	.no-results {
		display: flex;
		justify-content: center;
		padding: var(--space-lg);
	}

	.no-results p {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		margin: 0;
	}

	.fermentables-list {
		display: flex;
		flex-direction: column;
	}

	.ferm-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-md);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.ferm-main {
		display: flex;
		flex-direction: column;
		gap: 2px;
		flex: 1 1 200px;
		min-width: 0;
	}

	.ferm-info {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}

	.ferm-name {
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		overflow-wrap: anywhere;
	}

	.ferm-type {
		padding: 1px var(--space-xs);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
	}

	.ferm-details {
		display: flex;
		flex-wrap: wrap;
		gap: 0 var(--space-sm);
	}

	.detail {
		font-size: var(--text-xs);
		color: var(--ink-muted);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
	}

	.ferm-controls {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		margin-left: auto;
	}

	.amount-input input {
		width: 88px;
		text-align: right;
	}

	.percent {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		min-width: 4ch;
		text-align: right;
	}

	.type-group {
		display: flex;
		flex-direction: column;
	}

	.type-name {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0;
		padding: var(--space-2xs) 0;
		border-bottom: 1px solid var(--rule-strong);
	}

	.library-item.added {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.item-maltster {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	.item-color {
		display: flex;
		align-items: center;
		gap: var(--space-2xs);
	}

	.color-dot {
		width: 12px;
		height: 12px;
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
	}

	@media (max-width: 760px) {
		.ferm-controls {
			width: 100%;
			justify-content: space-between;
		}

		.ferm-controls .percent {
			margin-left: auto;
		}
	}
</style>
