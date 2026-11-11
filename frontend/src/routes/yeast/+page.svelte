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
				<span class="strain-count"><span class="num">{filteredStrains().length}</span> of <span class="num">{strains.length}</span></span>
			{/if}
		</div>
		<div class="header-actions">
			<button type="button" class="refresh-btn" onclick={handleRefresh} disabled={refreshing}>
				<svg class="icon" class:spinning={refreshing} aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
			<p class="error-message" role="alert">{error}</p>
			<button type="button" class="retry-btn" onclick={loadData}>Retry</button>
		</div>
	{:else if strains.length === 0}
		<div class="empty-state">
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
				<section class="producer-group">
					<h2 class="producer-name">{producer} <span class="producer-count">{groupStrains.length}</span></h2>
					<div class="scroll">
						<table class="ledger">
							<thead>
								<tr>
									<th>Strain</th>
									<th>Type</th>
									<th>Form</th>
									<th class="r">Attenuation</th>
									<th class="r">Temp range</th>
									<th>Flocculation</th>
									<th class="r"><span class="sr-only">Actions</span></th>
								</tr>
							</thead>
							<tbody>
								{#each groupStrains as strain (strain.id)}
									<tr>
										<td data-label="Strain">
											<div class="strain-name">{strain.name}{#if strain.is_custom} <span class="pill accent">Custom</span>{/if}</div>
											{#if strain.description}
												<p class="strain-description">{strain.description}</p>
											{/if}
										</td>
										<td data-label="Type">
											{#if strain.type}
												<span class="pill" style="color: {getTypeColor(strain.type)}; border-color: {getTypeColor(strain.type)}">{strain.type}</span>
											{:else}--{/if}
										</td>
										<td data-label="Form" class="muted cap">{strain.form || '--'}</td>
										<td data-label="Attenuation" class="r num">{formatAttenuation(strain.attenuation_low, strain.attenuation_high)}</td>
										<td data-label="Temp range" class="r num">{formatTempRange(strain.temp_low, strain.temp_high).replace('°C', '\u2009°C')}</td>
										<td data-label="Flocculation" class="muted cap">{strain.flocculation || '--'}</td>
										<td class="r actions">
											{#if strain.is_custom}
												<button
													type="button"
													class="delete-btn"
													onclick={() => (deleteTarget = strain)}
													aria-label="Delete {strain.name}"
												>Delete</button>
											{/if}
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				</section>
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
	.page-container { max-width: 1400px; margin: 0 auto; padding: var(--space-lg) var(--space-xl) var(--space-xl); }
	.page-header { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-md); margin-bottom: var(--space-md); }
	.header-left { display: flex; align-items: baseline; gap: var(--space-sm); }
	.page-title { font-family: var(--font-display); font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; color: var(--ink-primary); }
	.strain-count { font-size: var(--text-sm); color: var(--ink-secondary); }
	.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.header-actions { display: flex; gap: var(--space-sm); }
	.add-btn, .refresh-btn, .retry-btn { display: inline-flex; align-items: center; gap: var(--space-xs); min-height: 44px; padding: 0 var(--space-md); border-radius: 4px; font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; cursor: pointer; }
	.add-btn { background: var(--accent); color: var(--accent-ink); }
	.add-btn:hover { background: var(--accent-hover); }
	.refresh-btn, .retry-btn { background: var(--bg-surface); color: var(--ink-primary); border: 1px solid var(--rule-strong); }
	.refresh-btn:hover:not(:disabled), .retry-btn:hover { background: var(--accent-tint); border-color: var(--accent-rule); }
	.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }
	.add-btn:focus-visible, .refresh-btn:focus-visible, .retry-btn:focus-visible, .delete-btn:focus-visible, .btn-cancel:focus-visible, .btn-submit:focus-visible, .btn-delete:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.icon { width: 16px; height: 16px; }
	.icon.spinning { animation: spin 1s linear infinite; }
	@keyframes spin { to { transform: rotate(360deg); } }
	@media (prefers-reduced-motion: reduce) { .icon.spinning, .spinner { animation-duration: 3s; } }

	.filters-bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-sm); margin-bottom: var(--space-lg); }
	.search-input, .filter-select { min-height: 44px; padding: 0 var(--space-sm); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; color: var(--ink-primary); font-size: var(--text-sm); }
	.search-input { flex: 1; min-width: 200px; max-width: 20rem; }
	.search-input::placeholder { color: var(--ink-muted); }
	.filter-select { cursor: pointer; }
	.search-input:focus-visible, .filter-select:focus-visible, .form-group input:focus-visible, .form-group select:focus-visible, .form-group textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
	.custom-toggle { display: flex; align-items: center; gap: var(--space-xs); min-height: 44px; font-size: var(--text-sm); color: var(--ink-secondary); cursor: pointer; }
	.custom-toggle input { width: 16px; height: 16px; cursor: pointer; accent-color: var(--accent); }

	.loading-state, .empty-state, .error-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--space-2xl) var(--space-md); text-align: center; border-top: 1px solid var(--rule-hairline); border-bottom: 1px solid var(--rule-hairline); color: var(--ink-secondary); }
	.spinner { width: 32px; height: 32px; border: 3px solid var(--rule-hairline); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: var(--space-md); }
	.empty-title { font-family: var(--font-display); font-size: var(--text-lg); font-weight: 600; color: var(--ink-primary); margin-bottom: var(--space-xs); }
	.empty-description { font-size: var(--text-sm); color: var(--ink-secondary); }
	.error-message { color: var(--status-danger); margin-bottom: var(--space-md); padding: var(--space-xs) var(--space-sm); border: 1px solid color-mix(in oklch, var(--status-danger) 60%, transparent); border-radius: 4px; }

	.strains-list { display: flex; flex-direction: column; gap: var(--space-lg); }
	.producer-name { display: flex; align-items: baseline; gap: var(--space-xs); font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.07em; padding-bottom: var(--space-xs); border-bottom: 1px solid var(--rule-strong); }
	.producer-count { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-weight: 400; }
	.scroll { overflow-x: auto; }
	.ledger { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
	.ledger th { padding: var(--space-xs) var(--space-sm); text-align: left; font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); border-bottom: 1px solid var(--rule-hairline); white-space: nowrap; }
	.ledger td { padding: var(--space-sm); border-bottom: 1px solid var(--rule-hairline); color: var(--ink-primary); vertical-align: top; }
	.ledger .r { text-align: right; }
	.ledger .actions { white-space: nowrap; }
	.muted, .ledger td.muted { color: var(--ink-secondary); }
	.cap { text-transform: capitalize; }
	.sr-only { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
	.strain-name { font-weight: 700; color: var(--ink-primary); line-height: 1.3; }
	.strain-description { margin-top: var(--space-2xs); max-width: 60ch; font-size: var(--text-xs); color: var(--ink-muted); line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
	.pill { display: inline-flex; align-items: center; padding: 1px var(--space-xs); font-family: var(--font-display); font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); border: 1px solid var(--rule-strong); border-radius: 3px; line-height: 1.4; vertical-align: middle; }
	.pill.accent { color: var(--accent); border-color: var(--accent-rule); }
	.delete-btn { min-height: 32px; padding: 0 var(--space-xs); font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; color: var(--status-danger); border-radius: 4px; cursor: pointer; }
	.delete-btn:hover { text-decoration: underline; }

	.modal-overlay { position: fixed; inset: 0; background: color-mix(in oklch, var(--bg-canvas) 75%, transparent); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: var(--space-md); }
	.modal { background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; padding: var(--space-lg); max-width: 500px; width: 100%; max-height: 90vh; overflow-y: auto; }
	.modal-title { font-family: var(--font-display); font-size: var(--text-lg); font-weight: 700; color: var(--ink-primary); margin-bottom: var(--space-md); }
	.modal-text { font-size: var(--text-sm); color: var(--ink-secondary); margin-bottom: var(--space-lg); }
	.modal-form { display: flex; flex-direction: column; gap: var(--space-md); }
	.form-group { display: flex; flex-direction: column; gap: var(--space-2xs); }
	.form-group label { font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); }
	.form-group input, .form-group select, .form-group textarea { min-height: 44px; padding: 0 var(--space-sm); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; color: var(--ink-primary); font-size: var(--text-sm); }
	.form-group textarea { resize: vertical; min-height: 80px; padding: var(--space-xs) var(--space-sm); }
	.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-sm); }
	.modal-actions { display: flex; justify-content: flex-end; gap: var(--space-sm); margin-top: var(--space-md); }
	.btn-cancel, .btn-submit, .btn-delete { min-height: 44px; padding: 0 var(--space-md); border-radius: 4px; font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; cursor: pointer; }
	.btn-cancel { background: var(--bg-surface); border: 1px solid var(--rule-strong); color: var(--ink-primary); }
	.btn-cancel:hover { background: var(--accent-tint); border-color: var(--accent-rule); }
	.btn-submit { background: var(--accent); color: var(--accent-ink); }
	.btn-submit:hover:not(:disabled) { background: var(--accent-hover); }
	.btn-delete { background: var(--bg-surface); color: var(--status-danger); border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent); }
	.btn-delete:hover:not(:disabled) { background: var(--negative-muted); }
	.btn-submit:disabled, .btn-delete:disabled { opacity: 0.5; cursor: not-allowed; }

	@media (max-width: 640px) {
		.page-container { padding: var(--space-md); }
		.filters-bar { flex-direction: column; align-items: stretch; }
		.search-input { max-width: none; }
		.form-row { grid-template-columns: 1fr; }
		.ledger thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
		.ledger, .ledger tbody, .ledger tr, .ledger td { display: block; }
		.ledger tr { padding: var(--space-xs) 0; border-bottom: 1px solid var(--rule-hairline); }
		.ledger td { display: flex; justify-content: space-between; align-items: baseline; gap: var(--space-md); padding: var(--space-2xs) var(--space-xs); border: 0; text-align: right; }
		.ledger td[data-label]::before { content: attr(data-label); font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); text-align: left; flex-shrink: 0; }
		.ledger td[data-label="Strain"] { display: block; text-align: left; }
		.ledger td[data-label="Strain"]::before { display: none; }
		.ledger .actions { justify-content: flex-end; }
		.delete-btn { min-height: 44px; padding: 0 var(--space-sm); }
	}
</style>
