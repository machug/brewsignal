<script lang="ts">
	import { onMount } from 'svelte';
	import type {
		YeastStrainResponse, YeastStrainCreate,
		HopVarietyResponse, HopVarietyCreate,
		FermentableResponse, FermentableCreate
	} from '$lib/api';
	import {
		fetchYeastStrains, fetchYeastProducers, createYeastStrain, deleteYeastStrain, refreshYeastStrains,
		fetchHopVarieties, fetchHopOrigins, createHopVariety, deleteHopVariety, refreshHopVarieties,
		fetchFermentables, fetchFermentableTypes, fetchMaltsters, createFermentable, deleteFermentable, refreshFermentables
	} from '$lib/api';

	// Tab state
	type Tab = 'yeast' | 'hops' | 'fermentables';
	let activeTab = $state<Tab>('yeast');

	// Common state
	let loading = $state(true);
	let error = $state<string | null>(null);
	let searchQuery = $state('');
	let showCustomOnly = $state(false);
	let refreshing = $state(false);

	// Yeast state
	let yeastStrains = $state<YeastStrainResponse[]>([]);
	let yeastProducers = $state<string[]>([]);
	let yeastTypeFilter = $state('');
	let yeastProducerFilter = $state('');
	let showAddYeastModal = $state(false);
	let newYeast = $state<YeastStrainCreate>({
		name: '', producer: '', type: 'ale', form: 'dry',
		attenuation_low: undefined, attenuation_high: undefined,
		temp_low: undefined, temp_high: undefined,
		flocculation: 'medium', description: ''
	});

	// Hops state
	let hopVarieties = $state<HopVarietyResponse[]>([]);
	let hopOrigins = $state<string[]>([]);
	let hopPurposeFilter = $state('');
	let hopOriginFilter = $state('');
	let showAddHopModal = $state(false);
	let newHop = $state<HopVarietyCreate>({
		name: '', origin: '', alpha_acid_low: undefined, alpha_acid_high: undefined,
		beta_acid_low: undefined, beta_acid_high: undefined,
		purpose: 'dual', aroma_profile: '', substitutes: '', description: ''
	});

	// Fermentables state
	let fermentables = $state<FermentableResponse[]>([]);
	let fermentableTypes = $state<string[]>([]);
	let maltsters = $state<string[]>([]);
	let fermentableTypeFilter = $state('');
	let fermentableMaltsterFilter = $state('');
	let showAddFermentableModal = $state(false);
	let newFermentable = $state<FermentableCreate>({
		name: '', type: 'base', origin: '', maltster: '',
		color_srm: undefined, potential_sg: undefined,
		max_in_batch_percent: undefined, diastatic_power: undefined,
		flavor_profile: '', substitutes: '', description: ''
	});

	// Delete state
	let deleteTarget = $state<{ type: Tab; id: number; name: string } | null>(null);
	let deleting = $state(false);
	let saving = $state(false);

	// Filtered data
	let filteredYeast = $derived(() => {
		return yeastStrains.filter((s) => {
			const matchesSearch = !searchQuery ||
				s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				s.producer?.toLowerCase().includes(searchQuery.toLowerCase());
			const matchesType = !yeastTypeFilter || s.type === yeastTypeFilter;
			const matchesProducer = !yeastProducerFilter || s.producer === yeastProducerFilter;
			const matchesCustom = !showCustomOnly || s.is_custom;
			return matchesSearch && matchesType && matchesProducer && matchesCustom;
		});
	});

	let filteredHops = $derived(() => {
		return hopVarieties.filter((h) => {
			const matchesSearch = !searchQuery ||
				h.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				h.origin?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				h.aroma_profile?.toLowerCase().includes(searchQuery.toLowerCase());
			const matchesPurpose = !hopPurposeFilter || h.purpose === hopPurposeFilter;
			const matchesOrigin = !hopOriginFilter || h.origin === hopOriginFilter;
			const matchesCustom = !showCustomOnly || h.is_custom;
			return matchesSearch && matchesPurpose && matchesOrigin && matchesCustom;
		});
	});

	let filteredFermentables = $derived(() => {
		return fermentables.filter((f) => {
			const matchesSearch = !searchQuery ||
				f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
				f.maltster?.toLowerCase().includes(searchQuery.toLowerCase()) ||
				f.flavor_profile?.toLowerCase().includes(searchQuery.toLowerCase());
			const matchesType = !fermentableTypeFilter || f.type === fermentableTypeFilter;
			const matchesMaltster = !fermentableMaltsterFilter || f.maltster === fermentableMaltsterFilter;
			const matchesCustom = !showCustomOnly || f.is_custom;
			return matchesSearch && matchesType && matchesMaltster && matchesCustom;
		});
	});

	// Group yeast by producer
	let groupedYeast = $derived(() => {
		const groups: Record<string, YeastStrainResponse[]> = {};
		for (const strain of filteredYeast()) {
			const producer = strain.producer || 'Other';
			if (!groups[producer]) groups[producer] = [];
			groups[producer].push(strain);
		}
		return Object.fromEntries(Object.entries(groups).sort(([a], [b]) => a.localeCompare(b)));
	});

	// Group hops by origin
	let groupedHops = $derived(() => {
		const groups: Record<string, HopVarietyResponse[]> = {};
		for (const hop of filteredHops()) {
			const origin = hop.origin || 'Unknown';
			if (!groups[origin]) groups[origin] = [];
			groups[origin].push(hop);
		}
		return Object.fromEntries(Object.entries(groups).sort(([a], [b]) => a.localeCompare(b)));
	});

	// Group fermentables by type
	let groupedFermentables = $derived(() => {
		const groups: Record<string, FermentableResponse[]> = {};
		for (const f of filteredFermentables()) {
			const type = f.type || 'Other';
			if (!groups[type]) groups[type] = [];
			groups[type].push(f);
		}
		// Custom order: base first, then specialty, adjunct, sugar, extract, fruit, other
		const order = ['base', 'specialty', 'adjunct', 'sugar', 'extract', 'fruit', 'other'];
		return Object.fromEntries(
			Object.entries(groups).sort(([a], [b]) => {
				const aIdx = order.indexOf(a.toLowerCase());
				const bIdx = order.indexOf(b.toLowerCase());
				if (aIdx === -1 && bIdx === -1) return a.localeCompare(b);
				if (aIdx === -1) return 1;
				if (bIdx === -1) return -1;
				return aIdx - bIdx;
			})
		);
	});

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [yeastData, producersData, hopsData, originsData, fermData, typesData, maltstersData] = await Promise.all([
				fetchYeastStrains({ limit: 500 }),
				fetchYeastProducers(),
				fetchHopVarieties({ limit: 500 }),
				fetchHopOrigins(),
				fetchFermentables({ limit: 500 }),
				fetchFermentableTypes(),
				fetchMaltsters()
			]);
			yeastStrains = yeastData;
			yeastProducers = producersData.producers;
			hopVarieties = hopsData;
			hopOrigins = originsData.origins;
			fermentables = fermData;
			fermentableTypes = typesData.types;
			maltsters = maltstersData.maltsters;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load library data';
		} finally {
			loading = false;
		}
	}

	async function handleRefresh() {
		refreshing = true;
		try {
			if (activeTab === 'yeast') {
				await refreshYeastStrains();
			} else if (activeTab === 'hops') {
				await refreshHopVarieties();
			} else {
				await refreshFermentables();
			}
			await loadData();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to refresh';
		} finally {
			refreshing = false;
		}
	}

	async function handleAddYeast() {
		if (!newYeast.name.trim()) return;
		saving = true;
		try {
			const created = await createYeastStrain(newYeast);
			yeastStrains = [created, ...yeastStrains];
			showAddYeastModal = false;
			newYeast = { name: '', producer: '', type: 'ale', form: 'dry', attenuation_low: undefined, attenuation_high: undefined, temp_low: undefined, temp_high: undefined, flocculation: 'medium', description: '' };
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to add yeast';
		} finally {
			saving = false;
		}
	}

	async function handleAddHop() {
		if (!newHop.name.trim()) return;
		saving = true;
		try {
			const created = await createHopVariety(newHop);
			hopVarieties = [created, ...hopVarieties];
			showAddHopModal = false;
			newHop = { name: '', origin: '', alpha_acid_low: undefined, alpha_acid_high: undefined, beta_acid_low: undefined, beta_acid_high: undefined, purpose: 'dual', aroma_profile: '', substitutes: '', description: '' };
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to add hop';
		} finally {
			saving = false;
		}
	}

	async function handleAddFermentable() {
		if (!newFermentable.name.trim()) return;
		saving = true;
		try {
			const created = await createFermentable(newFermentable);
			fermentables = [created, ...fermentables];
			showAddFermentableModal = false;
			newFermentable = { name: '', type: 'base', origin: '', maltster: '', color_srm: undefined, potential_sg: undefined, max_in_batch_percent: undefined, diastatic_power: undefined, flavor_profile: '', substitutes: '', description: '' };
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to add fermentable';
		} finally {
			saving = false;
		}
	}

	async function handleDelete() {
		if (!deleteTarget) return;
		deleting = true;
		try {
			if (deleteTarget.type === 'yeast') {
				await deleteYeastStrain(deleteTarget.id);
				yeastStrains = yeastStrains.filter((s) => s.id !== deleteTarget!.id);
			} else if (deleteTarget.type === 'hops') {
				await deleteHopVariety(deleteTarget.id);
				hopVarieties = hopVarieties.filter((h) => h.id !== deleteTarget!.id);
			} else {
				await deleteFermentable(deleteTarget.id);
				fermentables = fermentables.filter((f) => f.id !== deleteTarget!.id);
			}
			deleteTarget = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete';
		} finally {
			deleting = false;
		}
	}

	function clearFilters() {
		searchQuery = '';
		showCustomOnly = false;
		yeastTypeFilter = '';
		yeastProducerFilter = '';
		hopPurposeFilter = '';
		hopOriginFilter = '';
		fermentableTypeFilter = '';
		fermentableMaltsterFilter = '';
	}

	function handleTabChange(tab: Tab) {
		activeTab = tab;
		clearFilters();
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

	function formatAlphaAcid(low?: number, high?: number): string {
		if (low == null && high == null) return '--';
		if (low != null && high != null) return `${low.toFixed(1)}-${high.toFixed(1)}%`;
		if (low != null) return `${low.toFixed(1)}%`;
		return `${high!.toFixed(1)}%`;
	}

	function getYeastTypeColor(type?: string): string {
		switch (type) {
			case 'ale': return 'var(--positive)';
			case 'lager': return 'var(--info)';
			case 'wine': return 'var(--warning)';
			case 'wild': return 'var(--negative)';
			default: return 'var(--text-secondary)';
		}
	}

	function getHopPurposeColor(purpose?: string): string {
		switch (purpose) {
			case 'bittering': return 'var(--warning)';
			case 'aroma': return 'var(--positive)';
			case 'dual': return 'var(--info)';
			default: return 'var(--text-secondary)';
		}
	}

	function getFermentableTypeColor(type?: string): string {
		switch (type?.toLowerCase()) {
			case 'base': return 'var(--positive)';
			case 'specialty': return 'var(--warning)';
			case 'adjunct': return 'var(--info)';
			case 'sugar': return 'var(--accent)';
			case 'extract': return 'var(--text-secondary)';
			default: return 'var(--text-muted)';
		}
	}

	function formatColor(srm?: number): string {
		if (srm == null) return '--';
		return `${srm.toFixed(1)} SRM`;
	}

	function getSrmColor(srm?: number): string {
		if (srm == null) return 'var(--text-muted)';
		if (srm <= 2) return '#F8F4B4';
		if (srm <= 4) return '#D9C939';
		if (srm <= 8) return '#BF923B';
		if (srm <= 15) return '#A85A3F';
		if (srm <= 25) return '#6B3A2C';
		if (srm <= 40) return '#4A2517';
		return '#1A0C0A';
	}

	onMount(loadData);
</script>

<svelte:head>
	<title>Library | BrewSignal</title>
</svelte:head>

<div class="page-container">
	<div class="page-header">
		<div class="header-left">
			<h1 class="page-title">Ingredient Library</h1>
		</div>
		<div class="header-actions">
			<button type="button" class="refresh-btn" onclick={handleRefresh} disabled={refreshing}>
				<svg class="icon" class:spinning={refreshing} fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
				</svg>
				{refreshing ? 'Refreshing...' : 'Refresh DB'}
			</button>
			<button type="button" class="add-btn" onclick={() => {
				if (activeTab === 'yeast') showAddYeastModal = true;
				else if (activeTab === 'hops') showAddHopModal = true;
				else showAddFermentableModal = true;
			}}>
				<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				Add Custom
			</button>
		</div>
	</div>

	<!-- Tabs -->
	<div class="tabs">
		<button type="button" class="tab" class:active={activeTab === 'yeast'} onclick={() => handleTabChange('yeast')}>
			Yeast
			<span class="tab-count">{yeastStrains.length}</span>
		</button>
		<button type="button" class="tab" class:active={activeTab === 'hops'} onclick={() => handleTabChange('hops')}>
			Hops
			<span class="tab-count">{hopVarieties.length}</span>
		</button>
		<button type="button" class="tab" class:active={activeTab === 'fermentables'} onclick={() => handleTabChange('fermentables')}>
			Fermentables
			<span class="tab-count">{fermentables.length}</span>
		</button>
	</div>

	<!-- Filters -->
	<div class="filters-bar">
		<input type="text" placeholder="Search..." bind:value={searchQuery} class="search-input" />

		{#if activeTab === 'yeast'}
			<select bind:value={yeastTypeFilter} class="filter-select">
				<option value="">All Types</option>
				<option value="ale">Ale</option>
				<option value="lager">Lager</option>
				<option value="wine">Wine</option>
				<option value="wild">Wild</option>
			</select>
			<select bind:value={yeastProducerFilter} class="filter-select">
				<option value="">All Producers</option>
				{#each yeastProducers as producer}
					<option value={producer}>{producer}</option>
				{/each}
			</select>
		{:else if activeTab === 'hops'}
			<select bind:value={hopPurposeFilter} class="filter-select">
				<option value="">All Purposes</option>
				<option value="bittering">Bittering</option>
				<option value="aroma">Aroma</option>
				<option value="dual">Dual Purpose</option>
			</select>
			<select bind:value={hopOriginFilter} class="filter-select">
				<option value="">All Origins</option>
				{#each hopOrigins as origin}
					<option value={origin}>{origin}</option>
				{/each}
			</select>
		{:else}
			<select bind:value={fermentableTypeFilter} class="filter-select">
				<option value="">All Types</option>
				{#each fermentableTypes as type}
					<option value={type}>{type}</option>
				{/each}
			</select>
			<select bind:value={fermentableMaltsterFilter} class="filter-select">
				<option value="">All Maltsters</option>
				{#each maltsters as m}
					<option value={m}>{m}</option>
				{/each}
			</select>
		{/if}

		<label class="custom-toggle">
			<input type="checkbox" bind:checked={showCustomOnly} />
			<span>Custom only</span>
		</label>
	</div>

	<!-- Content -->
	{#if loading}
		<div class="loading-state">
			<div class="spinner"></div>
			<p>Loading library...</p>
		</div>
	{:else if error}
		<div class="error-state">
			<p class="error-message">{error}</p>
			<button type="button" class="retry-btn" onclick={loadData}>Retry</button>
		</div>
	{:else if activeTab === 'yeast'}
		<!-- Yeast Content -->
		{#if filteredYeast().length === 0}
			<div class="empty-state">
				<p class="empty-description">No yeasts match your filters</p>
			</div>
		{:else}
			<div class="items-list">
				{#each Object.entries(groupedYeast()) as [producer, strains] (producer)}
					<div class="group">
						<h2 class="group-name">{producer} <span class="group-count">({strains.length})</span></h2>
						<div class="items-grid">
							{#each strains as strain (strain.id)}
								<div class="item-card" class:custom={strain.is_custom}>
									<div class="item-header">
										<h3 class="item-name">{strain.name}</h3>
										{#if strain.is_custom}
											<button type="button" class="delete-btn" onclick={() => (deleteTarget = { type: 'yeast', id: strain.id, name: strain.name })} aria-label="Delete">
												<svg class="icon-sm" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
												</svg>
											</button>
										{/if}
									</div>
									<div class="item-meta">
										{#if strain.type}
											<span class="item-type" style="color: {getYeastTypeColor(strain.type)}">{strain.type}</span>
										{/if}
										{#if strain.form}
											<span class="item-form">{strain.form}</span>
										{/if}
										{#if strain.is_custom}
											<span class="custom-badge">custom</span>
										{/if}
									</div>
									<div class="item-specs">
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
										<p class="item-description">{strain.description}</p>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{:else if activeTab === 'hops'}
		<!-- Hops Content -->
		{#if filteredHops().length === 0}
			<div class="empty-state">
				<p class="empty-description">No hops match your filters</p>
			</div>
		{:else}
			<div class="items-list">
				{#each Object.entries(groupedHops()) as [origin, hops] (origin)}
					<div class="group">
						<h2 class="group-name">{origin} <span class="group-count">({hops.length})</span></h2>
						<div class="items-grid">
							{#each hops as hop (hop.id)}
								<div class="item-card" class:custom={hop.is_custom}>
									<div class="item-header">
										<h3 class="item-name">{hop.name}</h3>
										{#if hop.is_custom}
											<button type="button" class="delete-btn" onclick={() => (deleteTarget = { type: 'hops', id: hop.id, name: hop.name })} aria-label="Delete">
												<svg class="icon-sm" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
												</svg>
											</button>
										{/if}
									</div>
									<div class="item-meta">
										{#if hop.purpose}
											<span class="item-type" style="color: {getHopPurposeColor(hop.purpose)}">{hop.purpose}</span>
										{/if}
										{#if hop.is_custom}
											<span class="custom-badge">custom</span>
										{/if}
									</div>
									<div class="item-specs">
										<div class="spec">
											<span class="spec-label">Alpha Acid</span>
											<span class="spec-value">{formatAlphaAcid(hop.alpha_acid_low, hop.alpha_acid_high)}</span>
										</div>
										{#if hop.beta_acid_low || hop.beta_acid_high}
											<div class="spec">
												<span class="spec-label">Beta Acid</span>
												<span class="spec-value">{formatAlphaAcid(hop.beta_acid_low, hop.beta_acid_high)}</span>
											</div>
										{/if}
									</div>
									{#if hop.aroma_profile}
										<p class="item-description">{hop.aroma_profile}</p>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{:else}
		<!-- Fermentables Content -->
		{#if filteredFermentables().length === 0}
			<div class="empty-state">
				<p class="empty-description">No fermentables match your filters</p>
			</div>
		{:else}
			<div class="items-list">
				{#each Object.entries(groupedFermentables()) as [type, items] (type)}
					<div class="group">
						<h2 class="group-name">{type} <span class="group-count">({items.length})</span></h2>
						<div class="items-grid">
							{#each items as item (item.id)}
								<div class="item-card" class:custom={item.is_custom}>
									<div class="item-header">
										<h3 class="item-name">{item.name}</h3>
										{#if item.is_custom}
											<button type="button" class="delete-btn" onclick={() => (deleteTarget = { type: 'fermentables', id: item.id, name: item.name })} aria-label="Delete">
												<svg class="icon-sm" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
													<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
												</svg>
											</button>
										{/if}
									</div>
									<div class="item-meta">
										{#if item.maltster}
											<span class="item-form">{item.maltster}</span>
										{/if}
										{#if item.origin}
											<span class="item-form">{item.origin}</span>
										{/if}
										{#if item.is_custom}
											<span class="custom-badge">custom</span>
										{/if}
									</div>
									<div class="item-specs">
										{#if item.color_srm != null}
											<div class="spec">
												<span class="spec-label">Color</span>
												<span class="spec-value" style="display: flex; align-items: center; gap: 4px;">
													<span class="color-swatch" style="background: {getSrmColor(item.color_srm)};"></span>
													{formatColor(item.color_srm)}
												</span>
											</div>
										{/if}
										{#if item.potential_sg != null}
											<div class="spec">
												<span class="spec-label">Potential</span>
												<span class="spec-value">{item.potential_sg.toFixed(3)}</span>
											</div>
										{/if}
										{#if item.max_in_batch_percent != null}
											<div class="spec">
												<span class="spec-label">Max %</span>
												<span class="spec-value">{item.max_in_batch_percent}%</span>
											</div>
										{/if}
										{#if item.diastatic_power != null}
											<div class="spec">
												<span class="spec-label">Diastatic</span>
												<span class="spec-value">{item.diastatic_power}°L</span>
											</div>
										{/if}
									</div>
									{#if item.flavor_profile}
										<p class="item-description">{item.flavor_profile}</p>
									{/if}
								</div>
							{/each}
						</div>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</div>

<!-- Add Yeast Modal -->
{#if showAddYeastModal}
	<div class="modal-overlay" onclick={() => (showAddYeastModal = false)} role="dialog" aria-modal="true">
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Add Custom Yeast</h2>
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
						<label for="yeast-atten-low">Attenuation Low (%)</label>
						<input id="yeast-atten-low" type="number" step="1" min="50" max="100" bind:value={newYeast.attenuation_low} />
					</div>
					<div class="form-group">
						<label for="yeast-atten-high">Attenuation High (%)</label>
						<input id="yeast-atten-high" type="number" step="1" min="50" max="100" bind:value={newYeast.attenuation_high} />
					</div>
				</div>
				<div class="form-group">
					<label for="yeast-desc">Description</label>
					<textarea id="yeast-desc" rows="2" bind:value={newYeast.description}></textarea>
				</div>
				<div class="modal-actions">
					<button type="button" class="btn-cancel" onclick={() => (showAddYeastModal = false)}>Cancel</button>
					<button type="submit" class="btn-submit" disabled={saving || !newYeast.name.trim()}>
						{saving ? 'Adding...' : 'Add Yeast'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- Add Hop Modal -->
{#if showAddHopModal}
	<div class="modal-overlay" onclick={() => (showAddHopModal = false)} role="dialog" aria-modal="true">
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Add Custom Hop</h2>
			<form class="modal-form" onsubmit={(e) => { e.preventDefault(); handleAddHop(); }}>
				<div class="form-group">
					<label for="hop-name">Name *</label>
					<input id="hop-name" type="text" bind:value={newHop.name} required />
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="hop-origin">Origin</label>
						<input id="hop-origin" type="text" bind:value={newHop.origin} />
					</div>
					<div class="form-group">
						<label for="hop-purpose">Purpose</label>
						<select id="hop-purpose" bind:value={newHop.purpose}>
							<option value="bittering">Bittering</option>
							<option value="aroma">Aroma</option>
							<option value="dual">Dual Purpose</option>
						</select>
					</div>
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="hop-alpha-low">Alpha Acid Low (%)</label>
						<input id="hop-alpha-low" type="number" step="0.1" min="0" max="30" bind:value={newHop.alpha_acid_low} />
					</div>
					<div class="form-group">
						<label for="hop-alpha-high">Alpha Acid High (%)</label>
						<input id="hop-alpha-high" type="number" step="0.1" min="0" max="30" bind:value={newHop.alpha_acid_high} />
					</div>
				</div>
				<div class="form-group">
					<label for="hop-aroma">Aroma Profile</label>
					<textarea id="hop-aroma" rows="2" bind:value={newHop.aroma_profile}></textarea>
				</div>
				<div class="modal-actions">
					<button type="button" class="btn-cancel" onclick={() => (showAddHopModal = false)}>Cancel</button>
					<button type="submit" class="btn-submit" disabled={saving || !newHop.name.trim()}>
						{saving ? 'Adding...' : 'Add Hop'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- Add Fermentable Modal -->
{#if showAddFermentableModal}
	<div class="modal-overlay" onclick={() => (showAddFermentableModal = false)} role="dialog" aria-modal="true">
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Add Custom Fermentable</h2>
			<form class="modal-form" onsubmit={(e) => { e.preventDefault(); handleAddFermentable(); }}>
				<div class="form-group">
					<label for="ferm-name">Name *</label>
					<input id="ferm-name" type="text" bind:value={newFermentable.name} required />
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="ferm-type">Type</label>
						<select id="ferm-type" bind:value={newFermentable.type}>
							<option value="base">Base</option>
							<option value="specialty">Specialty</option>
							<option value="adjunct">Adjunct</option>
							<option value="sugar">Sugar</option>
							<option value="extract">Extract</option>
							<option value="fruit">Fruit</option>
							<option value="other">Other</option>
						</select>
					</div>
					<div class="form-group">
						<label for="ferm-maltster">Maltster</label>
						<input id="ferm-maltster" type="text" bind:value={newFermentable.maltster} />
					</div>
				</div>
				<div class="form-row">
					<div class="form-group">
						<label for="ferm-color">Color (SRM)</label>
						<input id="ferm-color" type="number" step="0.1" min="0" max="600" bind:value={newFermentable.color_srm} />
					</div>
					<div class="form-group">
						<label for="ferm-potential">Potential SG</label>
						<input id="ferm-potential" type="number" step="0.001" min="1.000" max="1.100" bind:value={newFermentable.potential_sg} />
					</div>
				</div>
				<div class="form-group">
					<label for="ferm-flavor">Flavor Profile</label>
					<textarea id="ferm-flavor" rows="2" bind:value={newFermentable.flavor_profile}></textarea>
				</div>
				<div class="modal-actions">
					<button type="button" class="btn-cancel" onclick={() => (showAddFermentableModal = false)}>Cancel</button>
					<button type="submit" class="btn-submit" disabled={saving || !newFermentable.name.trim()}>
						{saving ? 'Adding...' : 'Add Fermentable'}
					</button>
				</div>
			</form>
		</div>
	</div>
{/if}

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<div class="modal-overlay" onclick={() => (deleteTarget = null)} role="dialog" aria-modal="true">
		<div class="modal" onclick={(e) => e.stopPropagation()}>
			<h2 class="modal-title">Delete {deleteTarget.type === 'yeast' ? 'Yeast' : deleteTarget.type === 'hops' ? 'Hop' : 'Fermentable'}?</h2>
			<p class="modal-text">Are you sure you want to delete "{deleteTarget.name}"? This cannot be undone.</p>
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

	.page-title {
		font-size: 28px;
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.header-actions {
		display: flex;
		gap: var(--space-3);
	}

	.add-btn, .refresh-btn {
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

	.add-btn:hover { background: var(--accent-hover); }

	.refresh-btn {
		background: var(--bg-elevated);
		color: var(--text-secondary);
		border: 1px solid var(--border-default);
	}

	.refresh-btn:hover:not(:disabled) {
		color: var(--text-primary);
		border-color: var(--text-muted);
	}

	.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }

	.icon { width: 16px; height: 16px; }
	.icon.spinning { animation: spin 1s linear infinite; }
	.icon-sm { width: 14px; height: 14px; }

	@keyframes spin { to { transform: rotate(360deg); } }

	/* Tabs */
	.tabs {
		display: flex;
		gap: var(--space-1);
		margin-bottom: var(--space-5);
		border-bottom: 1px solid var(--border-subtle);
		padding-bottom: var(--space-1);
	}

	.tab {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-2) var(--space-4);
		background: transparent;
		border: none;
		border-radius: 6px 6px 0 0;
		font-size: 14px;
		font-weight: 500;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all var(--transition);
	}

	.tab:hover { color: var(--text-primary); }

	.tab.active {
		color: var(--text-primary);
		background: var(--bg-elevated);
	}

	.tab-count {
		font-size: 11px;
		font-family: var(--font-mono);
		padding: 2px 6px;
		background: var(--bg-hover);
		border-radius: 4px;
		color: var(--text-muted);
	}

	.tab.active .tab-count {
		background: var(--accent);
		color: white;
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
	.loading-state, .empty-state, .error-state {
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

	/* Items List */
	.items-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-6);
	}

	.group {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.group-name {
		font-size: 14px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	.group-count {
		font-weight: 400;
		color: var(--text-muted);
	}

	.items-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
		gap: var(--space-3);
	}

	.item-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 8px;
		padding: var(--space-4);
		transition: border-color var(--transition);
	}

	.item-card:hover { border-color: var(--border-default); }

	.item-card.custom {
		border-color: var(--accent);
		background: rgba(59, 130, 246, 0.05);
	}

	.item-header {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		gap: var(--space-2);
		margin-bottom: var(--space-2);
	}

	.item-name {
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

	.item-meta {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-3);
	}

	.item-type {
		font-size: 11px;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.item-form {
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

	.item-specs {
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

	.color-swatch {
		width: 14px;
		height: 14px;
		border-radius: 3px;
		border: 1px solid var(--border-default);
	}

	.item-description {
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
		min-height: 60px;
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

	.btn-cancel, .btn-submit, .btn-delete {
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

	.btn-cancel:hover { background: var(--bg-hover); }

	.btn-submit {
		background: var(--accent);
		border: none;
		color: white;
	}

	.btn-submit:hover:not(:disabled) { background: var(--accent-hover); }
	.btn-submit:disabled { opacity: 0.5; cursor: not-allowed; }

	.btn-delete {
		background: var(--negative);
		border: none;
		color: white;
	}

	.btn-delete:hover:not(:disabled) { background: var(--negative); }
	.btn-delete:disabled { opacity: 0.5; cursor: not-allowed; }

	@media (max-width: 640px) {
		.page-header {
			flex-direction: column;
			align-items: flex-start;
			gap: var(--space-4);
		}

		.filters-bar { flex-direction: column; }
		.search-input { max-width: none; }
		.form-row { grid-template-columns: 1fr; }
		.tabs { overflow-x: auto; }
	}
</style>
