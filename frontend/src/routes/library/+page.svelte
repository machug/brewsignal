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

	// Detail modal state
	let selectedYeast = $state<YeastStrainResponse | null>(null);
	let selectedHop = $state<HopVarietyResponse | null>(null);
	let selectedFermentable = $state<FermentableResponse | null>(null);

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
		if (low != null && high != null) return `${low.toFixed(0)}\u2013${high.toFixed(0)}\u2009°C`;
		if (low != null) return `>${low.toFixed(0)}\u2009°C`;
		return `<${high!.toFixed(0)}\u2009°C`;
	}

	function formatAttenuation(low?: number, high?: number): string {
		if (low == null && high == null) return '--';
		if (low != null && high != null) {
			if (low === high) return `${low.toFixed(0)}%`;
			return `${low.toFixed(0)}\u2013${high.toFixed(0)}%`;
		}
		if (low != null) return `>${low.toFixed(0)}%`;
		return `<${high!.toFixed(0)}%`;
	}

	function formatAlphaAcid(low?: number, high?: number): string {
		if (low == null && high == null) return '--';
		if (low != null && high != null) return `${low.toFixed(1)}\u2013${high.toFixed(1)}%`;
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
		return `${srm.toFixed(1)}\u2009SRM`;
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

	function formatSourceName(source?: string): string {
		if (!source) return 'Unknown';
		switch (source) {
			case 'brewfather': return 'Brewfather';
			case 'beerxml': return 'BeerXML';
			case 'custom': return 'Custom';
			default: return source;
		}
	}

	function closeDetailModal() {
		selectedYeast = null;
		selectedHop = null;
		selectedFermentable = null;
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
				<svg class="icon" class:spinning={refreshing} aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
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
						<h2 class="group-name">{producer} <span class="group-count">{strains.length}</span></h2>
						<div class="row-head cols-yeast" aria-hidden="true"><span>Strain</span><span>Type</span><span class="r">Attenuation</span><span class="r">Temp range</span><span>Flocculation</span></div>
						<div class="items-grid">
							{#each strains as strain (strain.id)}
								<button type="button" class="item-row cols-yeast" class:custom={strain.is_custom} onclick={() => (selectedYeast = strain)}>
									<span class="c name">
										<span class="item-name">{strain.name}</span>
										{#if strain.is_custom}<span class="custom-badge">custom</span><span class="delete-btn" role="button" tabindex="-1" onclick={(e) => { e.stopPropagation(); deleteTarget = { type: 'yeast', id: strain.id, name: strain.name }; }} onkeydown={(e) => e.key === 'Enter' && (deleteTarget = { type: 'yeast', id: strain.id, name: strain.name })} aria-label="Delete {strain.name}">
											<svg class="icon-sm" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</span>{/if}
										{#if strain.description}<span class="item-description">{strain.description}</span>{/if}
									</span>
									<span class="c meta">
										{#if strain.type}<span class="item-type" style="color: {getYeastTypeColor(strain.type)}">{strain.type}</span>{/if}
										{#if strain.form}<span class="item-form">{strain.form}</span>{/if}
									</span>
									<span class="c r num v1"><span class="lbl">Attenuation</span>{formatAttenuation(strain.attenuation_low, strain.attenuation_high)}</span>
									<span class="c r num v2"><span class="lbl">Temperature range</span>{formatTempRange(strain.temp_low, strain.temp_high)}</span>
									<span class="c hide-phone"><span class="lbl">Flocculation</span><span class="cap">{strain.flocculation || '--'}</span></span>
								</button>
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
						<h2 class="group-name">{origin} <span class="group-count">{hops.length}</span></h2>
						<div class="row-head cols-hops" aria-hidden="true"><span>Hop</span><span>Purpose</span><span class="r">Alpha acid</span><span class="r">Beta acid</span></div>
						<div class="items-grid">
							{#each hops as hop (hop.id)}
								<button type="button" class="item-row cols-hops" class:custom={hop.is_custom} onclick={() => (selectedHop = hop)}>
									<span class="c name">
										<span class="item-name">{hop.name}</span>
										{#if hop.is_custom}<span class="custom-badge">custom</span><span class="delete-btn" role="button" tabindex="-1" onclick={(e) => { e.stopPropagation(); deleteTarget = { type: 'hops', id: hop.id, name: hop.name }; }} onkeydown={(e) => e.key === 'Enter' && (deleteTarget = { type: 'hops', id: hop.id, name: hop.name })} aria-label="Delete {hop.name}">
											<svg class="icon-sm" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</span>{/if}
										{#if hop.aroma_profile}<span class="item-description">{hop.aroma_profile}</span>{/if}
									</span>
									<span class="c meta">
										{#if hop.purpose}<span class="item-type" style="color: {getHopPurposeColor(hop.purpose)}">{hop.purpose}</span>{/if}
									</span>
									<span class="c r num v1"><span class="lbl">Alpha acid</span>{formatAlphaAcid(hop.alpha_acid_low, hop.alpha_acid_high)}</span>
									<span class="c r num v2"><span class="lbl">Beta acid</span>{hop.beta_acid_low || hop.beta_acid_high ? formatAlphaAcid(hop.beta_acid_low, hop.beta_acid_high) : '--'}</span>
								</button>
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
						<h2 class="group-name">{type} <span class="group-count">{items.length}</span></h2>
						<div class="row-head cols-ferm" aria-hidden="true"><span>Fermentable</span><span>Maltster / origin</span><span class="r">Colour</span><span class="r">Potential</span><span class="r">Max %</span><span class="r">Diastatic</span></div>
						<div class="items-grid">
							{#each items as item (item.id)}
								<button type="button" class="item-row cols-ferm" class:custom={item.is_custom} onclick={() => (selectedFermentable = item)}>
									<span class="c name">
										<span class="item-name">{item.name}</span>
										{#if item.is_custom}<span class="custom-badge">custom</span><span class="delete-btn" role="button" tabindex="-1" onclick={(e) => { e.stopPropagation(); deleteTarget = { type: 'fermentables', id: item.id, name: item.name }; }} onkeydown={(e) => e.key === 'Enter' && (deleteTarget = { type: 'fermentables', id: item.id, name: item.name })} aria-label="Delete {item.name}">
											<svg class="icon-sm" aria-hidden="true" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" /></svg>
										</span>{/if}
									</span>
									<span class="c meta"><span class="item-form">{[item.maltster, item.origin].filter(Boolean).join(' \u00b7 ') || '--'}</span></span>
									<span class="c r num v1"><span class="lbl">Colour</span>{#if item.color_srm != null}<span class="color-swatch" style="background: {getSrmColor(item.color_srm)};"></span> {formatColor(item.color_srm)}{:else}--{/if}</span>
									<span class="c r num v2"><span class="lbl">Potential</span>{item.potential_sg != null ? item.potential_sg.toFixed(3) : '--'}</span>
									<span class="c r num hide-phone"><span class="lbl">Maximum percent of batch</span>{item.max_in_batch_percent != null ? item.max_in_batch_percent + '%' : '--'}</span>
									<span class="c r num hide-phone"><span class="lbl">Diastatic power</span>{item.diastatic_power != null ? item.diastatic_power + '\u2009°L' : '--'}</span>
								</button>
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
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (showAddYeastModal = false)}
		onkeydown={(e) => e.key === 'Escape' && (showAddYeastModal = false)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="add-yeast-title" tabindex="-1">
			<h2 id="add-yeast-title" class="modal-title">Add Custom Yeast</h2>
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
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (showAddHopModal = false)}
		onkeydown={(e) => e.key === 'Escape' && (showAddHopModal = false)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="add-hop-title" tabindex="-1">
			<h2 id="add-hop-title" class="modal-title">Add Custom Hop</h2>
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
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (showAddFermentableModal = false)}
		onkeydown={(e) => e.key === 'Escape' && (showAddFermentableModal = false)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="add-fermentable-title" tabindex="-1">
			<h2 id="add-fermentable-title" class="modal-title">Add Custom Fermentable</h2>
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
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={() => (deleteTarget = null)}
		onkeydown={(e) => e.key === 'Escape' && (deleteTarget = null)}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="delete-library-title" tabindex="-1">
			<h2 id="delete-library-title" class="modal-title">Delete {deleteTarget.type === 'yeast' ? 'Yeast' : deleteTarget.type === 'hops' ? 'Hop' : 'Fermentable'}?</h2>
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

<!-- Yeast Detail Modal -->
{#if selectedYeast}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={closeDetailModal}
		onkeydown={(e) => e.key === 'Escape' && closeDetailModal()}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="detail-modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="yeast-detail-title" tabindex="-1">
			<div class="detail-header">
				<div class="detail-title-row">
					<h2 id="yeast-detail-title" class="detail-title">{selectedYeast.name}</h2>
					<button type="button" class="close-btn" onclick={closeDetailModal} aria-label="Close">
						<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
				<div class="detail-meta">
					{#if selectedYeast.producer}
						<span class="detail-producer">{selectedYeast.producer}</span>
					{/if}
					{#if selectedYeast.product_id}
						<span class="detail-product-id">{selectedYeast.product_id}</span>
					{/if}
					{#if selectedYeast.type}
						<span class="detail-type-badge" style="color: {getYeastTypeColor(selectedYeast.type)}">{selectedYeast.type}</span>
					{/if}
					{#if selectedYeast.form}
						<span class="detail-form">{selectedYeast.form}</span>
					{/if}
					{#if selectedYeast.is_custom}
						<span class="custom-badge">custom</span>
					{/if}
				</div>
			</div>

			<div class="detail-content">
				<div class="detail-specs-grid">
					<div class="detail-spec">
						<span class="detail-spec-label">Attenuation</span>
						<span class="detail-spec-value">{formatAttenuation(selectedYeast.attenuation_low, selectedYeast.attenuation_high)}</span>
					</div>
					<div class="detail-spec">
						<span class="detail-spec-label">Temp Range</span>
						<span class="detail-spec-value">{formatTempRange(selectedYeast.temp_low, selectedYeast.temp_high)}</span>
					</div>
					{#if selectedYeast.flocculation}
						<div class="detail-spec">
							<span class="detail-spec-label">Flocculation</span>
							<span class="detail-spec-value">{selectedYeast.flocculation}</span>
						</div>
					{/if}
					{#if selectedYeast.alcohol_tolerance}
						<div class="detail-spec">
							<span class="detail-spec-label">Alcohol Tolerance</span>
							<span class="detail-spec-value">{selectedYeast.alcohol_tolerance}%</span>
						</div>
					{/if}
				</div>

				{#if selectedYeast.description}
					<div class="detail-section">
						<h3 class="detail-section-title">Description</h3>
						<p class="detail-description">{selectedYeast.description}</p>
					</div>
				{/if}

				<div class="detail-footer">
					<span class="detail-source">Source: {formatSourceName(selectedYeast.source)}</span>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Hop Detail Modal -->
{#if selectedHop}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={closeDetailModal}
		onkeydown={(e) => e.key === 'Escape' && closeDetailModal()}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="detail-modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="hop-detail-title" tabindex="-1">
			<div class="detail-header">
				<div class="detail-title-row">
					<h2 id="hop-detail-title" class="detail-title">{selectedHop.name}</h2>
					<button type="button" class="close-btn" onclick={closeDetailModal} aria-label="Close">
						<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
				<div class="detail-meta">
					{#if selectedHop.origin}
						<span class="detail-producer">{selectedHop.origin}</span>
					{/if}
					{#if selectedHop.purpose}
						<span class="detail-type-badge" style="color: {getHopPurposeColor(selectedHop.purpose)}">{selectedHop.purpose}</span>
					{/if}
					{#if selectedHop.is_custom}
						<span class="custom-badge">custom</span>
					{/if}
				</div>
			</div>

			<div class="detail-content">
				<div class="detail-specs-grid">
					<div class="detail-spec">
						<span class="detail-spec-label">Alpha Acid</span>
						<span class="detail-spec-value">{formatAlphaAcid(selectedHop.alpha_acid_low, selectedHop.alpha_acid_high)}</span>
					</div>
					{#if selectedHop.beta_acid_low || selectedHop.beta_acid_high}
						<div class="detail-spec">
							<span class="detail-spec-label">Beta Acid</span>
							<span class="detail-spec-value">{formatAlphaAcid(selectedHop.beta_acid_low, selectedHop.beta_acid_high)}</span>
						</div>
					{/if}
				</div>

				{#if selectedHop.aroma_profile}
					<div class="detail-section">
						<h3 class="detail-section-title">Aroma Profile</h3>
						<p class="detail-description">{selectedHop.aroma_profile}</p>
					</div>
				{/if}

				{#if selectedHop.substitutes}
					<div class="detail-section">
						<h3 class="detail-section-title">Substitutes</h3>
						<p class="detail-substitutes">{selectedHop.substitutes}</p>
					</div>
				{/if}

				{#if selectedHop.description}
					<div class="detail-section">
						<h3 class="detail-section-title">Description</h3>
						<p class="detail-description">{selectedHop.description}</p>
					</div>
				{/if}

				<div class="detail-footer">
					<span class="detail-source">Source: {formatSourceName(selectedHop.source)}</span>
				</div>
			</div>
		</div>
	</div>
{/if}

<!-- Fermentable Detail Modal -->
{#if selectedFermentable}
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="modal-overlay"
		onclick={closeDetailModal}
		onkeydown={(e) => e.key === 'Escape' && closeDetailModal()}
		role="presentation"
	>
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="detail-modal" onclick={(e) => e.stopPropagation()} onkeydown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="fermentable-detail-title" tabindex="-1">
			<div class="detail-header">
				<div class="detail-title-row">
					<h2 id="fermentable-detail-title" class="detail-title">{selectedFermentable.name}</h2>
					<button type="button" class="close-btn" onclick={closeDetailModal} aria-label="Close">
						<svg class="icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
				<div class="detail-meta">
					{#if selectedFermentable.maltster}
						<span class="detail-producer">{selectedFermentable.maltster}</span>
					{/if}
					{#if selectedFermentable.origin}
						<span class="detail-origin">{selectedFermentable.origin}</span>
					{/if}
					{#if selectedFermentable.type}
						<span class="detail-type-badge" style="color: {getFermentableTypeColor(selectedFermentable.type)}">{selectedFermentable.type}</span>
					{/if}
					{#if selectedFermentable.is_custom}
						<span class="custom-badge">custom</span>
					{/if}
				</div>
			</div>

			<div class="detail-content">
				<div class="detail-specs-grid">
					{#if selectedFermentable.color_srm != null}
						<div class="detail-spec">
							<span class="detail-spec-label">Color</span>
							<span class="detail-spec-value" style="display: flex; align-items: center; gap: 6px;">
								<span class="color-swatch-lg" style="background: {getSrmColor(selectedFermentable.color_srm)};"></span>
								{formatColor(selectedFermentable.color_srm)}
							</span>
						</div>
					{/if}
					{#if selectedFermentable.potential_sg != null}
						<div class="detail-spec">
							<span class="detail-spec-label">Potential SG</span>
							<span class="detail-spec-value">{selectedFermentable.potential_sg.toFixed(3)}</span>
						</div>
					{/if}
					{#if selectedFermentable.max_in_batch_percent != null}
						<div class="detail-spec">
							<span class="detail-spec-label">Max in Batch</span>
							<span class="detail-spec-value">{selectedFermentable.max_in_batch_percent}%</span>
						</div>
					{/if}
					{#if selectedFermentable.diastatic_power != null}
						<div class="detail-spec">
							<span class="detail-spec-label">Diastatic Power</span>
							<span class="detail-spec-value">{selectedFermentable.diastatic_power}°L</span>
						</div>
					{/if}
				</div>

				{#if selectedFermentable.flavor_profile}
					<div class="detail-section">
						<h3 class="detail-section-title">Flavor Profile</h3>
						<p class="detail-description">{selectedFermentable.flavor_profile}</p>
					</div>
				{/if}

				{#if selectedFermentable.substitutes}
					<div class="detail-section">
						<h3 class="detail-section-title">Substitutes</h3>
						<p class="detail-substitutes">{selectedFermentable.substitutes}</p>
					</div>
				{/if}

				{#if selectedFermentable.description}
					<div class="detail-section">
						<h3 class="detail-section-title">Description</h3>
						<p class="detail-description">{selectedFermentable.description}</p>
					</div>
				{/if}

				<div class="detail-footer">
					<span class="detail-source">Source: {formatSourceName(selectedFermentable.source)}</span>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	.page-container { max-width: 1400px; margin: 0 auto; padding: var(--space-lg) var(--space-xl) var(--space-xl); }
	.page-header { display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-md); margin-bottom: var(--space-md); }
	.page-title { font-family: var(--font-display); font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; color: var(--ink-primary); }
	.header-actions { display: flex; gap: var(--space-sm); }
	.add-btn, .refresh-btn, .retry-btn { display: inline-flex; align-items: center; gap: var(--space-xs); min-height: 44px; padding: 0 var(--space-md); border-radius: 4px; font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; cursor: pointer; }
	.add-btn { background: var(--accent); color: var(--accent-ink); }
	.add-btn:hover { background: var(--accent-hover); }
	.refresh-btn, .retry-btn { background: var(--bg-surface); color: var(--ink-primary); border: 1px solid var(--rule-strong); }
	.refresh-btn:hover:not(:disabled), .retry-btn:hover { background: var(--accent-tint); border-color: var(--accent-rule); }
	.refresh-btn:disabled { opacity: 0.6; cursor: not-allowed; }
	.add-btn:focus-visible, .refresh-btn:focus-visible, .retry-btn:focus-visible, .tab:focus-visible, .item-card:focus-visible, .close-btn:focus-visible, .btn-cancel:focus-visible, .btn-submit:focus-visible, .btn-delete:focus-visible, .delete-btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.icon { width: 16px; height: 16px; }
	.icon.spinning { animation: spin 1s linear infinite; }
	.icon-sm { width: 14px; height: 14px; }
	@keyframes spin { to { transform: rotate(360deg); } }
	@media (prefers-reduced-motion: reduce) { .icon.spinning, .spinner { animation-duration: 3s; } }

	.tabs { display: flex; flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: none; box-shadow: inset 0 -1px 0 var(--rule-hairline); margin-bottom: var(--space-md); }
	.tabs::-webkit-scrollbar { display: none; }
	.tab { display: inline-flex; align-items: center; gap: var(--space-xs); min-height: 44px; padding: 0 var(--space-md); font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; color: var(--ink-secondary); border-bottom: 2px solid transparent; cursor: pointer; transition: color 140ms var(--ease-out-quart); white-space: nowrap; flex-shrink: 0; }
	.tab:hover { color: var(--ink-primary); }
	.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
	.tab-count { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size: var(--text-xs); color: var(--ink-muted); }

	/* Filters as quiet chips */
	.filters-bar { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-xs); margin-bottom: var(--space-lg); }
	.search-input { flex: 1; min-width: 200px; max-width: 20rem; min-height: 44px; padding: 0 var(--space-sm); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; color: var(--ink-primary); font-size: var(--text-sm); }
	.search-input::placeholder { color: var(--ink-muted); }
	.filter-select { min-height: 44px; padding: 0 var(--space-sm); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; color: var(--ink-secondary); font-size: var(--text-sm); cursor: pointer; }
	.filter-select:hover { border-color: var(--rule-strong); color: var(--ink-primary); }
	.search-input:focus-visible, .filter-select:focus-visible, .form-group input:focus-visible, .form-group select:focus-visible, .form-group textarea:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
	.custom-toggle { display: flex; align-items: center; gap: var(--space-xs); min-height: 44px; padding: 0 var(--space-sm); font-size: var(--text-sm); color: var(--ink-secondary); border: 1px solid var(--rule-strong); background: var(--bg-surface); border-radius: 4px; cursor: pointer; }
	.custom-toggle:has(input:checked) { color: var(--accent); border-color: var(--accent-rule); background: var(--accent-tint); }
	.custom-toggle input { width: 16px; height: 16px; cursor: pointer; accent-color: var(--accent); }

	.loading-state, .empty-state, .error-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: var(--space-2xl) var(--space-md); text-align: center; border-top: 1px solid var(--rule-hairline); border-bottom: 1px solid var(--rule-hairline); color: var(--ink-secondary); }
	.spinner { width: 32px; height: 32px; border: 3px solid var(--rule-hairline); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.8s linear infinite; margin-bottom: var(--space-md); }
	.empty-description { font-size: var(--text-sm); color: var(--ink-secondary); }
	.error-message { color: var(--status-danger); margin-bottom: var(--space-md); padding: var(--space-xs) var(--space-sm); border: 1px solid color-mix(in oklch, var(--status-danger) 60%, transparent); border-radius: 4px; }

	/* Ledger of rows (each item is a button row) */
	.items-list { display: flex; flex-direction: column; gap: var(--space-lg); }
	.group-name { display: flex; align-items: baseline; gap: var(--space-xs); font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.07em; padding-bottom: var(--space-xs); border-bottom: 1px solid var(--rule-strong); }
	.group-count { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-weight: 400; }
	.group { min-width: 0; }
	.items-grid { display: flex; flex-direction: column; }
	.row-head, .item-row { display: grid; column-gap: var(--space-md); align-items: center; padding-left: var(--space-xs); padding-right: var(--space-xs); }
	.cols-yeast { grid-template-columns: minmax(14rem, 2fr) 9rem 7rem 8rem 7rem; }
	.cols-hops { grid-template-columns: minmax(14rem, 2fr) 9rem 8rem 8rem; }
	.cols-ferm { grid-template-columns: minmax(14rem, 2fr) minmax(8rem, 1.2fr) 8rem 6rem 5rem 6rem; }
	.row-head { padding-top: var(--space-xs); padding-bottom: var(--space-xs); border-bottom: 1px solid var(--rule-hairline); font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); }
	.r { text-align: right; }
	@media (max-width: 1040px) {
		.cols-yeast { grid-template-columns: minmax(9rem, 2fr) 7rem 6rem 7rem 5rem; column-gap: var(--space-sm); }
		.cols-hops { grid-template-columns: minmax(9rem, 2fr) 7rem 6rem 6rem; column-gap: var(--space-sm); }
		.cols-ferm { grid-template-columns: minmax(9rem, 2fr) minmax(5rem, 1fr) 7rem 5rem 4rem 5rem; column-gap: var(--space-sm); }
	}
	.item-row { width: 100%; padding-top: var(--space-sm); padding-bottom: var(--space-sm); text-align: left; background: transparent; border-bottom: 1px solid var(--rule-hairline); border-radius: 0; cursor: pointer; transition: background-color 140ms var(--ease-out-quart); font-size: var(--text-sm); color: var(--ink-primary); }
	.item-row:hover { background: var(--bg-surface); }
	.c { min-width: 0; }
	.name { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-2xs) var(--space-xs); }
	.item-name { font-size: var(--text-sm); font-weight: 700; color: var(--ink-primary); line-height: 1.3; }
	.item-description { flex-basis: 100%; max-width: 70ch; font-size: var(--text-xs); color: var(--ink-muted); line-height: 1.5; font-weight: 400; display: -webkit-box; -webkit-line-clamp: 1; line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; }
	.delete-btn { display: inline-flex; align-items: center; justify-content: center; min-width: 32px; min-height: 32px; color: var(--ink-secondary); border-radius: 4px; cursor: pointer; }
	.delete-btn:hover, .delete-btn:focus-visible { color: var(--status-danger); background: var(--negative-muted); }
	.meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-xs); }
	.item-type, .custom-badge, .detail-type-badge { display: inline-flex; align-items: center; padding: 1px var(--space-xs); font-family: var(--font-display); font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; border: 1px solid currentColor; border-radius: 3px; line-height: 1.4; }
	.custom-badge { color: var(--accent); border-color: var(--accent-rule); }
	.item-form { font-size: var(--text-xs); color: var(--ink-secondary); text-transform: capitalize; }
	.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.cap { text-transform: capitalize; }
	.lbl { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
	.item-row .c { position: relative; }
	.color-swatch { display: inline-block; width: 12px; height: 12px; border-radius: 2px; border: 1px solid var(--rule-strong); vertical-align: -1px; }

	/* Modals */
	.modal-overlay { position: fixed; inset: 0; background: color-mix(in oklch, var(--bg-canvas) 75%, transparent); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: var(--space-md); }
	.modal, .detail-modal { background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; width: 100%; max-height: 90vh; overflow-y: auto; }
	.modal { padding: var(--space-lg); max-width: 500px; }
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

	/* Detail modal */
	.detail-modal { max-width: 560px; }
	.detail-header { padding: var(--space-lg) var(--space-lg) var(--space-md); border-bottom: 1px solid var(--rule-hairline); }
	.detail-title-row { display: flex; justify-content: space-between; align-items: flex-start; gap: var(--space-md); margin-bottom: var(--space-xs); }
	.detail-title { font-family: var(--font-display); font-size: var(--text-lg); font-weight: 700; color: var(--ink-primary); line-height: 1.25; }
	.close-btn { flex-shrink: 0; display: inline-flex; align-items: center; justify-content: center; width: 44px; height: 44px; margin: -10px -10px 0 0; color: var(--ink-muted); border-radius: 4px; cursor: pointer; }
	.close-btn:hover { color: var(--ink-primary); background: var(--bg-elevated); }
	.detail-meta { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-xs) var(--space-sm); }
	.detail-producer { font-size: var(--text-sm); color: var(--ink-secondary); }
	.detail-product-id { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size: var(--text-xs); color: var(--ink-muted); }
	.detail-origin { font-size: var(--text-sm); color: var(--ink-secondary); }
	.detail-form { font-size: var(--text-xs); color: var(--ink-muted); text-transform: capitalize; }
	.detail-content { padding: var(--space-md) var(--space-lg) var(--space-lg); }
	.detail-specs-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); border: 1px solid var(--rule-strong); border-radius: 4px; margin-bottom: var(--space-md); }
	.detail-spec { display: flex; flex-direction: column; gap: 2px; padding: var(--space-sm) var(--space-md); border-bottom: 1px solid var(--rule-hairline); }
	.detail-spec:nth-child(odd) { border-right: 1px solid var(--rule-hairline); }
	.detail-spec:nth-last-child(-n + 2) { border-bottom: 0; }
	.detail-spec-label { font-family: var(--font-display); font-size: 0.6875rem; font-weight: 600; color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.07em; }
	.detail-spec-value { text-transform: capitalize; display: flex; align-items: center; gap: var(--space-xs); font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size: var(--text-base); color: var(--ink-primary); }
	.detail-section { margin-bottom: var(--space-md); padding-top: var(--space-sm); border-top: 1px solid var(--rule-hairline); }
	.detail-section-title { font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); margin-bottom: var(--space-xs); }
	.detail-description { max-width: 68ch; font-size: var(--text-sm); color: var(--ink-secondary); line-height: 1.6; }
	.detail-substitutes { font-size: var(--text-sm); color: var(--ink-secondary); }
	.detail-footer { padding-top: var(--space-sm); border-top: 1px solid var(--rule-hairline); }
	.detail-source { font-size: var(--text-xs); color: var(--ink-muted); }
	.color-swatch-lg { display: inline-block; width: 18px; height: 18px; border-radius: 2px; border: 1px solid var(--rule-strong); }

	@media (max-width: 760px) {
		.page-container { padding: var(--space-md); }
		.tabs { padding-right: 28px; -webkit-mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 28px), transparent); mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 28px), transparent); }
		.filters-bar { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
		.search-input { grid-column: 1 / -1; max-width: none; min-width: 0; }
		.filter-select { min-width: 0; width: 100%; }
		.custom-toggle { grid-column: 1 / -1; min-height: 44px; padding: 0; border: 0; background: transparent; }
		.custom-toggle:has(input:checked) { background: transparent; border: 0; }
		.form-row { grid-template-columns: 1fr; }
		.row-head { display: none; }
		.item-row { grid-template-columns: 1fr auto; grid-template-areas: "name v1" "meta v2"; gap: 4px 12px; padding: 12px 0; align-items: start; }
		.name { grid-area: name; }
		.meta { grid-area: meta; }
		.v1 { grid-area: v1; }
		.v2 { grid-area: v2; font-size: var(--text-xs); }
		.hide-phone, .item-description { display: none; }
		.detail-modal { max-height: 94vh; }
		.detail-header { padding: var(--space-md); }
		.detail-content { padding: var(--space-md); }
	}
</style>
