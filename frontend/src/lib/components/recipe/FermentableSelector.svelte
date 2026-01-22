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
			color_srm: f.color_srm || 2
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

	function getTypeColor(type?: string): string {
		switch (type?.toLowerCase()) {
			case 'base':
				return 'var(--positive)';
			case 'specialty':
				return 'var(--warning)';
			case 'adjunct':
				return 'var(--info)';
			case 'sugar':
				return 'var(--accent-primary)';
			case 'extract':
				return 'var(--text-secondary)';
			default:
				return 'var(--text-tertiary)';
		}
	}
</script>

<div class="fermentable-selector">
	<div class="selector-header">
		<div class="header-left">
			<h3>
				<span class="header-icon" aria-hidden="true">
					<svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
						<path d="M12 3v18" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
						<ellipse cx="9" cy="7" rx="2" ry="3" fill="currentColor" opacity="0.7" />
						<ellipse cx="15" cy="9" rx="2" ry="3" fill="currentColor" opacity="0.6" />
						<ellipse cx="9" cy="13" rx="2" ry="3" fill="currentColor" opacity="0.55" />
						<ellipse cx="15" cy="15" rx="2" ry="3" fill="currentColor" opacity="0.5" />
					</svg>
				</span>
				Grain Bill
			</h3>
			{#if fermentables.length > 0}
				<span class="stats">
					{totalKg.toFixed(2)} kg · OG {recipeStats().og.toFixed(3)} ·
					<span class="color-swatch" style="background-color: {recipeStats().color_hex}"></span>
					{recipeStats().srm.toFixed(0)} SRM
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
								<span class="ferm-type" style="color: {getTypeColor(ferm.type)}">
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
								value={ferm.amount_kg}
								onchange={(e) => updateAmount(ferm.id, parseFloat(e.currentTarget.value) || 0)}
							/>
							<span class="unit">kg</span>
						</div>
						<span class="percent">{getPercent(ferm.amount_kg)}</span>
						<button type="button" class="remove-btn" onclick={() => removeFermentable(ferm.id)}>
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
					<button type="button" class="close-btn" onclick={() => (showBrowser = false)}>×</button>
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
													{ferm.color_srm.toFixed(0)}°L
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
		--section-accent: var(--recipe-accent);
		--section-accent-strong: rgba(245, 158, 11, 0.35);
		--section-accent-soft: rgba(245, 158, 11, 0.18);
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
		background: rgba(245, 158, 11, 0.18);
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
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.color-swatch {
		width: 16px;
		height: 16px;
		border-radius: 4px;
		border: 1px solid var(--border-default);
		box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.1);
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

	.fermentables-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.ferm-item {
		position: relative;
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: var(--space-3) var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		transition: border-color var(--transition), transform var(--transition), box-shadow var(--transition);
		overflow: hidden;
	}

	.ferm-item::before {
		content: '';
		position: absolute;
		inset: 0 auto 0 0;
		width: 3px;
		background: var(--section-accent);
		opacity: 0.35;
	}

	.ferm-item:hover {
		border-color: var(--section-accent);
		transform: translateY(-1px);
		box-shadow: 0 10px 20px rgba(0, 0, 0, 0.35);
	}

	.ferm-main {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.ferm-info {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.ferm-name {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.ferm-type {
		font-size: 10px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.ferm-details {
		display: flex;
		gap: var(--space-3);
	}

	.detail {
		font-size: 12px;
		color: var(--text-tertiary);
		font-family: var(--font-mono);
	}

	.ferm-controls {
		display: flex;
		align-items: center;
		gap: var(--space-3);
	}

	.amount-input {
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.amount-input input {
		width: 70px;
		padding: var(--space-2);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 14px;
		font-family: var(--font-mono);
		text-align: right;
	}

	.amount-input input:focus {
		outline: none;
		border-color: var(--accent-primary);
	}

	.unit {
		font-size: 12px;
		color: var(--text-secondary);
	}

	.percent {
		font-size: 13px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
		min-width: 50px;
		text-align: right;
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

	.type-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.type-name {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-secondary);
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

	.library-item:hover:not(:disabled) {
		border-color: var(--section-accent);
		background: var(--bg-hover);
		box-shadow: inset 0 0 0 1px var(--section-accent-soft);
	}

	.library-item.added {
		opacity: 0.5;
		cursor: not-allowed;
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

	.item-maltster {
		font-size: 12px;
		color: var(--text-tertiary);
	}

	.item-details {
		display: flex;
		gap: var(--space-3);
		align-items: center;
	}

	.item-color {
		display: flex;
		align-items: center;
		gap: var(--space-1);
		font-size: 12px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.color-dot {
		width: 12px;
		height: 12px;
		border-radius: 2px;
		border: 1px solid var(--border-subtle);
	}

	.item-potential {
		font-size: 12px;
		color: var(--text-tertiary);
		font-family: var(--font-mono);
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
</style>
