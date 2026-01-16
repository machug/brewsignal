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
				fetchYeastStrains(),
				fetchYeastProducers()
			]);
			strains = strainsData;
			producers = producersData;
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
		if (low != null && high != null) return `${low.toFixed(0)}-${high.toFixed(0)}°C`;
		if (low != null) return `>${low.toFixed(0)}°C`;
		return `<${high!.toFixed(0)}°C`;
	}

	function formatAttenuation(low?: number, high?: number): string {
		if (low == null && high == null) return '';
		if (low != null && high != null) return `${low.toFixed(0)}-${high.toFixed(0)}%`;
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
				return 'var(--text-secondary)';
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
			<div class="spinner"></div>
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
		gap: var(--space-3);
		padding: var(--space-4);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
	}

	.selector-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.selector-label {
		font-size: 14px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.clear-btn {
		font-size: 12px;
		color: var(--text-secondary);
		background: transparent;
		border: none;
		cursor: pointer;
		padding: var(--space-1) var(--space-2);
		transition: color var(--transition);
	}

	.clear-btn:hover {
		color: var(--accent-primary);
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

	.empty,
	.no-results {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-6);
	}

	.empty-text,
	.no-results p {
		font-size: 14px;
		color: var(--text-secondary);
		margin: 0;
	}

	.error-box {
		padding: var(--space-4);
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

	.selected-yeast {
		padding: var(--space-4);
		background: var(--bg-surface);
		border: 1px solid var(--accent-primary);
		border-radius: 6px;
	}

	.yeast-info {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.yeast-header {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.yeast-name {
		font-size: 16px;
		font-weight: 600;
		color: var(--text-primary);
		margin: 0;
	}

	.yeast-type {
		font-size: 11px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.yeast-producer {
		font-size: 13px;
		color: var(--text-secondary);
		margin: 0;
	}

	.yeast-specs {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-3);
	}

	.spec {
		font-size: 12px;
		color: var(--text-secondary);
		font-family: var(--font-mono);
	}

	.filters {
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
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

	.strain-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
		max-height: 350px;
		overflow-y: auto;
	}

	.producer-group {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
	}

	.producer-name {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.5px;
		margin: 0;
		padding: var(--space-1) 0;
		border-bottom: 1px solid var(--border-subtle);
	}

	.strain-item {
		display: flex;
		flex-direction: column;
		gap: var(--space-1);
		padding: var(--space-3);
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 4px;
		text-align: left;
		cursor: pointer;
		transition: all var(--transition);
	}

	.strain-item:hover {
		border-color: var(--accent-primary);
		background: var(--bg-hover);
	}

	.strain-main {
		display: flex;
		align-items: center;
		gap: var(--space-2);
	}

	.strain-name {
		font-size: 14px;
		color: var(--text-primary);
		flex: 1;
	}

	.strain-type {
		font-size: 10px;
		font-weight: 500;
		text-transform: uppercase;
		letter-spacing: 0.5px;
	}

	.strain-details {
		display: flex;
		gap: var(--space-3);
	}

	.detail {
		font-size: 11px;
		color: var(--text-tertiary);
		font-family: var(--font-mono);
	}
</style>
