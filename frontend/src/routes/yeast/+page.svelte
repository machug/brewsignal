<script lang="ts">
	import { onMount } from 'svelte';
	import type { YeastStrainResponse, YeastStrainCreate } from '$lib/api';
	import { fetchYeastStrains, fetchYeastProducers, createYeastStrain, deleteYeastStrain, refreshYeastStrains } from '$lib/api';

	let strains = $state<YeastStrainResponse[]>([]);
	let producers = $state<string[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');
	let typeFilter = $state('');
	let producerFilter = $state('');
	let showCustomOnly = $state(false);

	// Add custom yeast modal state
	let showAddModal = $state(false);
	let newYeast = $state<YeastStrainCreate>({
		name: '',
		producer: '',
		type: 'ale',
		form: 'dry',
		attenuation_low: undefined,
		attenuation_high: undefined,
		temp_low: undefined,
		temp_high: undefined,
		flocculation: 'medium',
		description: ''
	});
	let saving = $state(false);
	let refreshing = $state(false);

	// Delete confirmation
	let deleteTarget = $state<YeastStrainResponse | null>(null);
	let deleting = $state(false);

	let filteredStrains = $derived(() => {
		return strains.filter((s) => {
			const matchesSearch =
				!searchQuery ||
				s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				s.producer?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				s.product_id?.toLowerCase().includes(searchQuery.toLowerCase());

			const matchesType = !typeFilter || s.type === typeFilter;
			const matchesProducer = !producerFilter || s.producer === producerFilter;
			const matchesCustom = !showCustomOnly || s.is_custom;

			return matchesSearch && matchesType && matchesProducer && matchesCustom;
		});
	});

	// Group by producer for display
	let groupedStrains = $derived(() => {
		const groups: Record<string, YeastStrainResponse[]> = {};
		for (const strain of filteredStrains()) {
			const producer = strain.producer || 'Other';
			if (!groups[producer]) {
				groups[producer] = [];
			}
			groups[producer].push(strain);
		}
		return Object.fromEntries(
			Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
		);
	});

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [strainsData, producersData] = await Promise.all([
				fetchYeastStrains({ limit: 500 }),
				fetchYeastProducers()
			]);
			strains = strainsData;
			producers = producersData.producers;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load yeast strains';
		} finally {
			loading = false;
		}
	}

	async function handleAddYeast() {
		if (!newYeast.name.trim()) return;
		saving = true;
		try {
			const created = await createYeastStrain(newYeast);
			strains = [created, ...strains];
			showAddModal = false;
			newYeast = {
				name: '',
				producer: '',
				type: 'ale',
				form: 'dry',
				attenuation_low: undefined,
				attenuation_high: undefined,
				temp_low: undefined,
				temp_high: undefined,
				flocculation: 'medium',
				description: ''
			};
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to add yeast';
		} finally {
			saving = false;
		}
	}

	async function handleDelete() {
		if (!deleteTarget) return;
		deleting = true;
		try {
			await deleteYeastStrain(deleteTarget.id);
			strains = strains.filter((s) => s.id !== deleteTarget!.id);
			deleteTarget = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete yeast';
		} finally {
			deleting = false;
		}
	}

	async function handleRefresh() {
		refreshing = true;
		try {
			const result = await refreshYeastStrains();
			await loadData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to refresh yeast database';
		} finally {
			refreshing = false;
		}
	}

	function formatTempRange(low?: number, high?: number): string {
		if (low == null && high == null) return '--';
		if (low != null && high != null) return `${low.toFixed(0)}-${high.toFixed(0)}°C`;
		if (low != null) return `>${low.toFixed(0)}°C`;
		return `<${high!.toFixed(0)}°C`;
	}

	function formatAttenuation(low?: number, high?: number): string {
		if (low == null && high == null) return '--';
		if (low != null && high != null) {
			if (low === high) return `${low.toFixed(0)}%`;
			return `${low.toFixed(0)}-${high.toFixed(0)}%`;
		}
		if (low != null) return `>${low.toFixed(0)}%`;
		return `<${high!.toFixed(0)}%`;
	}

	function getTypeColor(type?: string): string {
		switch (type) {
			case 'ale': return 'var(--positive)';
			case 'lager': return 'var(--info)';
			case 'wine': return 'var(--warning)';
			case 'wild': return 'var(--negative)';
			default: return 'var(--text-secondary)';
		}
	}

	onMount(loadData);
</script>

<svelte:head>
	<title>Yeast Library | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<div class="header-left">
			<h1 class="page-title">Yeast Library</h1>
			{#if !loading && strains.length > 0}
				<span class="strain-count">{filteredStrains().length} of {strains.length}</span>
			{/if}
		</div>
		<div class="header-actions">
			<button type="button" class="refresh-btn" onclick={handleRefresh} disabled={refreshing}>
				<svg class="icon" class:spinning={refreshing} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
				</svg>
				{refreshing ? 'Refreshing...' : 'Refresh DB'}
			</button>
			<button type="button" class="add-btn" onclick={() => (showAddModal = true)}>
				<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				Add Custom
			</button>
		</div>
	</div>

	<!-- Filters -->
	<div class="filters-bar">
		<input
			type="text"
			placeholder="Search yeasts..."
			bind:value={searchQuery}
			class="search-input"
		/>
		<select bind:value={typeFilter} class="filter-select">
			<option value="">All Types</option>
			<option value="ale">Ale</option>
			<option value="lager">Lager</option>
			<option value="wine">Wine</option>
			<option value="wild">Wild</option>
		</select>
		<select bind:value={producerFilter} class="filter-select">
			<option value="">All Producers</option>
			{#each producers as producer}
				<option value={producer}>{producer}</option>
			{/each}
		</select>
		<label class="custom-toggle">
			<input type="checkbox" bind:checked={showCustomOnly} />
			<span>Custom only</span>
		</label>
	</div>

	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading yeast strains...</p>
		</div>
	{:else if error}
		<div class="error-state">
			<p class="error-message">{error}</p>
			<button type="button" class="retry-btn" onclick={loadData}>Retry</button>
		</div>
	{:else if strains.length === 0}
		<div class="empty-state">
			<div class="empty-icon">🧫</div>
			<h2 class="empty-title">No Yeast Strains</h2>
			<p class="empty-description">Click "Refresh DB" to load the yeast database</p>
		</div>
	{:else if filteredStrains().length === 0}
		<div class="empty-state">
			<p class="empty-description">No yeasts match your filters</p>
		</div>
	{:else}
		<div class="strains-list">
			{#each Object.entries(groupedStrains()) as [producer, groupStrains] (producer)}
				<div class="producer-group">
					<h2 class="producer-name">{producer} <span class="producer-count">({groupStrains.length})</span></h2>
					<div class="strains-grid">
						{#each groupStrains as strain (strain.id)}
							<div class="strain-card" class:custom={strain.is_custom}>
								<div class="strain-header">
									<h3 class="strain-name">{strain.name}</h3>
									{#if strain.is_custom}
										<button
											type="button"
											class="delete-btn"
											onclick={() => (deleteTarget = strain)}
											aria-label="Delete"
										>
											<svg class="icon-sm" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
												<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
											</svg>
										</button>
									{/if}
								</div>
								<div class="strain-meta">
									{#if strain.type}
										<span class="strain-type" style="color: {getTypeColor(strain.type)}">{strain.type}</span>
									{/if}
									{#if strain.form}
										<span class="strain-form">{strain.form}</span>
									{/if}
									{#if strain.is_custom}
										<span class="custom-badge">custom</span>
									{/if}
								</div>
								<div class="strain-specs">
									<div class="spec">
										<span class="spec-label">Attenuation</span>
										<span class="spec-value">{formatAttenuation(strain.attenuation_low, strain.attenuation_high)}</span>
									</div>
									<div class="spec">
										<span class="spec-label">Temp Range</span>
										<span class="spec-value">{formatTempRange(strain.temp_low, strain.temp_high)}</span>
									</div>
									{#if strain.flocculation}
										<div class="spec">
											<span class="spec-label">Flocculation</span>
											<span class="spec-value">{strain.flocculation}</span>
										</div>
									{/if}
								</div>
								{#if strain.description}
									<p class="strain-description">{strain.description}</p>
								{/if}
							</div>
						{/each}
					</div>
				</div>
			{/each}
		</div>
	{/if}
</div>

<!-- Add Custom Yeast Modal -->
{#if showAddModal}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (showAddModal = false)}
		onkeydown={(e) => e.key === 'Escape' && (showAddModal = false)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="add-yeast-modal-title" tabindex="-1">
			<h2 id="add-yeast-modal-title" class="modal-title">Add Custom Yeast</h2>
			<form class="modal-form" onsubmit={(e) => { e.preventDefault(); handleAddYeast(); }}>
				<div class="form-group">
					<label for="yeast-name">Name *</label>
					<input id="yeast-name" type="text" bind:value={newYeast.name} required />
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="yeast-producer">Producer</label>
						<input id="yeast-producer" type="text" bind:value={newYeast.producer} />
					</div>
					<div class="form-group">
						<label for="yeast-type">Type</label>
						<select id="yeast-type" bind:value={newYeast.type}>
							<option value="ale">Ale</option>
							<option value="lager">Lager</option>
							<option value="wine">Wine</option>
							<option value="wild">Wild</option>
						</select>
					</div>
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="yeast-form">Form</label>
						<select id="yeast-form" bind:value={newYeast.form}>
							<option value="dry">Dry</option>
							<option value="liquid">Liquid</option>
							<option value="slant">Slant</option>
						</select>
					</div>
					<div class="form-group">
						<label for="yeast-floc">Flocculation</label>
						<select id="yeast-floc" bind:value={newYeast.flocculation}>
							<option value="low">Low</option>
							<option value="medium">Medium</option>
							<option value="high">High</option>
							<option value="very high">Very High</option>
						</select>
					</div>
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="yeast-atten-low">Attenuation Low (%)</label>
						<input id="yeast-atten-low" type="number" step="1" min="50" max="100" bind:value={newYeast.attenuation_low} />
					</div>
					<div class="form-group">
						<label for="yeast-atten-high">Attenuation High (%)</label>
						<input id="yeast-atten-high" type="number" step="1" min="50" max="100" bind:value={newYeast.attenuation_high} />
					</div>
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="yeast-temp-low">Temp Low (°C)</label>
						<input id="yeast-temp-low" type="number" step="0.5" min="0" max="40" bind:value={newYeast.temp_low} />
					</div>
					<div class="form-group">
						<label for="yeast-temp-high">Temp High (°C)</label>
						<input id="yeast-temp-high" type="number" step="0.5" min="0" max="40" bind:value={newYeast.temp_high} />
					</div>
				</div>
				<div class="form-group">
					<label for="yeast-desc">Description</label>
					<textarea id="yeast-desc" rows="3" bind:value={newYeast.description}></textarea>
				</div>
				<div class="modal-actions">
					<button type="button" class="btn-cancel" onclick={() => (showAddModal = false)}>Cancel</button>
					<button type="submit" class="btn-submit" disabled={saving || !newYeast.name.trim()}>
						{saving ? 'Adding...' : 'Add Yeast'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (deleteTarget = null)}
		onkeydown={(e) => e.key === 'Escape' && (deleteTarget = null)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="delete-yeast-title" tabindex="-1">
			<h2 id="delete-yeast-title" class="modal-title">Delete Yeast?</h2>
			<p class="modal-text">
				Are you sure you want to delete "{deleteTarget.name}"? This cannot be undone.
			</p>
			<div class="modal-actions">
				<button type="button" class="btn-cancel" onclick={() => (deleteTarget = null)}>Cancel</button>
				<button type="button" class="btn-delete" onclick={handleDelete} disabled={deleting}>
					{deleting ? 'Deleting...' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container {
		max-width: 1400px;
		margin: 0 auto;
		padding: var(--space-6);
	}

	.page-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: var(--space-5);
	}

	.header-left {
		display: flex;
		align-items: baseline;
		gap: var(--space-3);
	}

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.strain-count {
		font-size: 14px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.header-actions {
		display: flex;
		gap: var(--space-3);
	}

	.add-btn,
	.refresh-btn {
		display: inline-flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-4);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
	}

	.add-btn {
		background: var(--accent);
		color: white;
		border: none;
	}

	.add-btn:hover {
		background: var(--accent-hover);
	}

	.refresh-btn {
		background: var(--bg-elevated);
		color: var(--text-secondary);
		border: 1px solid var(--border-default);
	}

	.refresh-btn:hover:not(:disabled) {
		color: var(--text-primary);
		border-color: var(--text-muted);
	}

	.refresh-btn:disabled {
		opacity: 0.6;
		cursor: not-allowed;
	}

	.icon {
		width: 16px;
		height: 16px;
	}

	.icon.spinning {
		animation: spin 1s linear infinite;
	}

	.icon-sm {
		width: 14px;
		height: 14px;
	}

	@keyframes spin {
		to { transform: rotate(360deg); }
	}

	/* Filters */
	.filters-bar {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
		margin-bottom: var(--space-6);
	}

	.search-input {
		flex: 1;
		min-width: 200px;
		max-width: 300px;
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
	}

	.search-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.filter-select {
		padding: var(--space-2) var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
		cursor: pointer;
	}

	.filter-select:focus {
		outline: none;
		border-color: var(--accent);
	}

	.custom-toggle {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.custom-toggle input {
		width: 16px;
		height: 16px;
		cursor: pointer;
	}

	/* States */
	.loading-state,
	.empty-state,
	.error-state {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: var(--space-12);
		text-align: center;
	}

	.spinner {
		width: 32px;
		height: 32px;
		border: 3px solid var(--gray-700);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
		margin-bottom: var(--space-4);
	}

	.empty-icon {
		font-size: 48px;
		margin-bottom: var(--space-4);
	}

	.empty-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 var(--space-2) 0;
	}

	.empty-description {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.error-message {
		color: var(--negative);
		margin-bottom: var(--space-4);
	}

	.retry-btn {
		padding: var(--space-2) var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		cursor: pointer;
	}

	/* Strains List */
	.strains-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.producer-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.producer-name {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	.producer-count {
		font-weight: 400;
		color: var(--text-muted);
	}

	.strains-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: var(--space-3);
	}

	.strain-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		padding: var(--space-4);
		transition: border-color var(--transition);
	}

	.strain-card:hover {
		border-color: var(--border-default);
	}

	.strain-card.custom {
		border-color: var(--accent);
		background: rgba(59, 130, 246, 0.05);
	}

	.strain-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-2);
		margin-bottom: var(--space-2);
	}

	.strain-name {
		font-size: 15px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
		line-height: 1.3;
	}

	.delete-btn {
		flex-shrink: 0;
		padding: var(--space-1);
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		border-radius: 4px;
		transition: all var(--transition);
	}

	.delete-btn:hover {
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
	}

	.strain-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}

	.strain-type {
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.strain-form {
		font-size: 11px;
		color: var(--text-muted);
		text-transform: capitalize;
	}

	.custom-badge {
		font-size: 10px;
		font-weight: 500;
		color: var(--accent);
		background: rgba(59, 130, 246, 0.15);
		padding: 2px 6px;
		border-radius: 4px;
	}

	.strain-specs {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-4);
		margin-bottom: var(--space-3);
	}

	.spec {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.spec-label {
		font-size: 10px;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
	}

	.spec-value {
		font-size: 13px;
		font-family: var(--font-mono);
		color: var(--text-secondary);
	}

	.strain-description {
		font-size: 12px;
		color: var(--text-muted);
		line-height: 1.5;
		margin: 0;
		display: -webkit-box;
		-webkit-line-clamp: 3;
		-webkit-box-orient: vertical;
		overflow: hidden;
	}

	/* Modal */
	.modal-overlay {
		position: fixed;
		inset: 0;
		background: rgba(0, 0, 0, 0.6);
		display: flex;
		align-items: center;
		justify-content: center;
		z-index: 1000;
		padding: var(--space-4);
	}

	.modal {
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 12px;
		padding: var(--space-6);
		max-width: 500px;
		width: 100%;
		max-height: 90vh;
		overflow-y: auto;
	}

	.modal-title {
		font-size: 20px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0 0 var(--space-4) 0;
	}

	.modal-text {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0 0 var(--space-6) 0;
	}

	.modal-form {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.form-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.form-group label {
		font-size: 13px;
		font-weight: 500;
		color: var(--text-secondary);
	}

	.form-group input,
	.form-group select,
	.form-group textarea {
		padding: var(--space-2) var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 6px;
		color: var(--text-primary);
		font-size: 14px;
	}

	.form-group input:focus,
	.form-group select:focus,
	.form-group textarea:focus {
		outline: none;
		border-color: var(--accent);
	}

	.form-group textarea {
		resize: vertical;
		min-height: 80px;
	}

	.form-row {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: var(--space-3);
	}

	.modal-actions {
		display: flex;
		justify-content: flex-end;
		gap: var(--space-3);
		margin-top: var(--space-4);
	}

	.btn-cancel,
	.btn-submit,
	.btn-delete {
		padding: var(--space-2) var(--space-4);
		border-radius: 6px;
		font-size: 14px;
		font-weight: 500;
		cursor: pointer;
		transition: all var(--transition);
	}

	.btn-cancel {
		background: transparent;
		border: 1px solid var(--border-default);
		color: var(--text-primary);
	}

	.btn-cancel:hover {
		background: var(--bg-hover);
	}

	.btn-submit {
		background: var(--accent);
		border: none;
		color: white;
	}

	.btn-submit:hover:not(:disabled) {
		background: var(--accent-hover);
	}

	.btn-submit:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.btn-delete {
		background: var(--negative);
		border: none;
		color: white;
	}

	.btn-delete:hover:not(:disabled) {
		background: var(--negative);
	}

	.btn-delete:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	@media (max-width: 640px) {
		.page-header {
			flex-direction: column;
			align-items: flex-start;
			gap: var(--space-4);
		}

		.filters-bar {
			flex-direction: column;
		}

		.search-input {
			max-width: none;
		}

		.form-row {
			grid-template-columns: 1fr;
		}
	}
</style>
