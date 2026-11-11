<script lang="ts">
	import { onMount } from 'svelte';
	import type { YeastStrainResponse } from '$lib/api';
	import { fetchYeastStrains, fetchYeastProducers } from '$lib/api';

	interface Props {
		selectedYeastId?: number;
		onSelect: (yeast: YeastStrainResponse | null) => void;
		label?: string;
	}

	let { selectedYeastId, onSelect, label = 'Select Yeast Strain (Optional)' }: Props = $props();

	let strains = $state<YeastStrainResponse[]>([]);
	let producers = $state<string[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');
	let typeFilter = $state<string>('');
	let producerFilter = $state<string>('');

	// Filter strains based on search and filters
	let filteredStrains = $derived(() => {
		return strains.filter((s) => {
			// Text search
			const matchesSearch =
				!searchQuery ||
				s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				s.producer?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				s.product_id?.toLowerCase().includes(searchQuery.toLowerCase());

			// Type filter
			const matchesType = !typeFilter || s.type === typeFilter;

			// Producer filter
			const matchesProducer = !producerFilter || s.producer === producerFilter;

			return matchesSearch && matchesType && matchesProducer;
		});
	});

	// Group filtered strains by producer
	let groupedStrains = $derived(() => {
		const groups: Record<string, YeastStrainResponse[]> = {};
		for (const strain of filteredStrains()) {
			const producer = strain.producer || 'Other';
			if (!groups[producer]) {
				groups[producer] = [];
			}
			groups[producer].push(strain);
		}
		// Sort groups alphabetically
		return Object.fromEntries(
			Object.entries(groups).sort(([a], [b]) => a.localeCompare(b))
		);
	});

	let selectedYeast = $derived(
		selectedYeastId ? strains.find((s) => s.id === selectedYeastId) : null
	);

	onMount(async () => {
		try {
			const [strainsData, producersData] = await Promise.all([
				fetchYeastStrains({ limit: 500 }),
				fetchYeastProducers()
			]);
			strains = strainsData;
			producers = producersData.producers;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load yeast strains';
			console.error('Failed to load yeast strains:', e);
		} finally {
			loading = false;
		}
	});

	function handleSelect(yeast: YeastStrainResponse) {
		onSelect(yeast);
	}

	function handleClear() {
		onSelect(null);
	}

	function formatTempRange(low?: number, high?: number): string {
		if (low == null && high == null) return '';
		if (low != null && high != null) return `${low.toFixed(0)}\u2013${high.toFixed(0)}\u2009°C`;
		if (low != null) return `>${low.toFixed(0)}\u2009°C`;
		return `<${high!.toFixed(0)}\u2009°C`;
	}

	function formatAttenuation(low?: number, high?: number): string {
		if (low == null && high == null) return '';
		if (low != null && high != null) return `${low.toFixed(0)}\u2013${high.toFixed(0)}%`;
		if (low != null) return `>${low.toFixed(0)}%`;
		return `<${high!.toFixed(0)}%`;
	}

	function getTypeColor(type?: string): string {
		switch (type) {
			case 'ale':
				return 'var(--positive)';
			case 'lager':
				return 'var(--info)';
			case 'wine':
				return 'var(--warning)';
			case 'wild':
				return 'var(--negative)';
			default:
				return 'var(--ink-secondary)';
		}
	}
</script>

<div class="yeast-selector">
	<div class="selector-header">
		<label for="yeast-search" class="selector-label">{label}</label>
		{#if selectedYeast}
			<button type="button" class="clear-btn" onclick={handleClear}>Clear Selection</button>
		{/if}
	</div>

	{#if loading}
		<div class="loading">
			<div class="spinner" aria-hidden="true"></div>
			<p>Loading yeast strains...</p>
		</div>
	{:else if error}
		<div class="error-box">
			<p class="error-text">{error}</p>
		</div>
	{:else if strains.length === 0}
		<div class="empty">
			<p class="empty-text">No yeast strains available.</p>
		</div>
	{:else}
		{#if selectedYeast}
			<div class="selected-yeast">
				<div class="yeast-info">
					<div class="yeast-header">
						<p class="yeast-name">{selectedYeast.name}</p>
						{#if selectedYeast.type}
							<span class="yeast-type" style="color: {getTypeColor(selectedYeast.type)}">
								{selectedYeast.type}
							</span>
						{/if}
					</div>
					{#if selectedYeast.producer}
						<p class="yeast-producer">{selectedYeast.producer}</p>
					{/if}
					<div class="yeast-specs">
						{#if selectedYeast.attenuation_low || selectedYeast.attenuation_high}
							<span class="spec">
								Attn: {formatAttenuation(selectedYeast.attenuation_low, selectedYeast.attenuation_high)}
							</span>
						{/if}
						{#if selectedYeast.temp_low || selectedYeast.temp_high}
							<span class="spec">
								Temp: {formatTempRange(selectedYeast.temp_low, selectedYeast.temp_high)}
							</span>
						{/if}
						{#if selectedYeast.flocculation}
							<span class="spec">Floc: {selectedYeast.flocculation}</span>
						{/if}
					</div>
				</div>
			</div>
		{:else}
			<div class="filters">
				<input
					id="yeast-search"
					aria-label="Search yeast strains"
					type="text"
					placeholder="Search yeast strains..."
					bind:value={searchQuery}
					class="search-input"
				/>
				<div class="filter-row">
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
				</div>
			</div>

			<div class="strain-list">
				{#each Object.entries(groupedStrains()) as [producer, strainGroup] (producer)}
					<div class="producer-group">
						<h4 class="producer-name">{producer}</h4>
						{#each strainGroup as strain (strain.id)}
							<button type="button" class="strain-item" onclick={() => handleSelect(strain)}>
								<div class="strain-main">
									<span class="strain-name">{strain.name}</span>
									{#if strain.type}
										<span class="strain-type" style="color: {getTypeColor(strain.type)}">
											{strain.type}
										</span>
									{/if}
								</div>
								<div class="strain-details">
									{#if strain.attenuation_low || strain.attenuation_high}
										<span class="detail">
											{formatAttenuation(strain.attenuation_low, strain.attenuation_high)}
										</span>
									{/if}
									{#if strain.temp_low || strain.temp_high}
										<span class="detail">
											{formatTempRange(strain.temp_low, strain.temp_high)}
										</span>
									{/if}
								</div>
							</button>
						{/each}
					</div>
				{/each}
				{#if Object.keys(groupedStrains()).length === 0}
					<div class="no-results">
						<p>No strains match your filters</p>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<style>
	.yeast-selector {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		min-width: 0;
	}
	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.selector-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.clear-btn {
		min-height: 44px;
		padding: 0 var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		cursor: pointer;
	}
	.clear-btn:hover {
		color: var(--accent);
	}
	.loading,
	.empty,
	.no-results {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-xs);
		padding: var(--space-lg);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.spinner {
		width: 24px;
		height: 24px;
		border: 2px solid var(--rule-hairline);
		border-top-color: var(--accent);
		border-radius: 50%;
		animation: spin 0.8s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	.empty-text,
	.no-results p {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.error-box {
		padding: var(--space-sm);
		border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent);
	}
	.error-text {
		font-size: var(--text-sm);
		color: var(--status-danger);
		text-align: center;
	}
	.selected-yeast {
		padding: var(--space-sm) 0;
		border-top: 1px solid var(--accent-rule);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.yeast-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}
	.yeast-header {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.yeast-name {
		font-family: var(--font-display);
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.yeast-type,
	.strain-type {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.yeast-producer {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.yeast-specs,
	.strain-details {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-sm);
	}
	.spec,
	.detail {
		font-size: var(--text-xs);
		color: var(--ink-secondary);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
	}
	.filters {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}
	.search-input,
	.filter-select {
		width: 100%;
		min-height: 44px;
		padding: 0 var(--space-sm);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-size: var(--text-sm);
	}
	.search-input:focus,
	.filter-select:focus {
		outline: none;
		border-color: var(--accent);
	}
	.filter-row {
		display: flex;
		gap: var(--space-xs);
	}
	.filter-select {
		flex: 1;
		min-width: 0;
	}
	.strain-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
		max-height: 350px;
		overflow-y: auto;
	}
	.producer-name {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		padding: var(--space-2xs) 0;
		border-bottom: 1px solid var(--rule-strong);
	}
	.strain-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		width: 100%;
		min-height: 44px;
		padding: var(--space-xs) var(--space-2xs);
		border-bottom: 1px solid var(--rule-hairline);
		text-align: left;
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.strain-item:hover {
		background: var(--bg-surface);
	}
	.strain-main {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.strain-name {
		font-size: var(--text-sm);
		color: var(--ink-primary);
		flex: 1;
	}
	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation: none;
		}
	}
</style>
