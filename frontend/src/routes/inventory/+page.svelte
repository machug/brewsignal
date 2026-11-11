<script lang="ts">
	import { onMount } from 'svelte';
	import type {
		EquipmentResponse,
		EquipmentCreate,
		HopInventoryResponse,
		HopInventoryCreate,
		YeastInventoryResponse,
		YeastInventoryCreate,
		HopSummary,
		YeastInventorySummary,
		YeastStrainResponse,
		HopVarietyResponse,
		EquipmentType,
		HopForm,
		YeastInventoryForm
	} from '$lib/api';
	import {
		fetchEquipment,
		createEquipment,
		updateEquipment,
		deleteEquipment,
		fetchHopInventory,
		fetchHopSummary,
		createHopInventory,
		updateHopInventory,
		deleteHopInventory,
		adjustHopAmount,
		fetchYeastInventory,
		fetchYeastInventorySummary,
		fetchExpiringYeast,
		createYeastInventory,
		updateYeastInventory,
		deleteYeastInventory,
		useYeast,
		fetchYeastStrains,
		fetchHopVarieties
	} from '$lib/api';

	type Tab = 'equipment' | 'hops' | 'yeast';

	let activeTab = $state<Tab>('hops');
	let loading = $state(true);
	let error = $state<string | null>(null);

	// Equipment state
	let equipment = $state<EquipmentResponse[]>([]);
	let showEquipmentModal = $state(false);
	let editingEquipment = $state<EquipmentResponse | null>(null);
	let newEquipment = $state<EquipmentCreate>({
		name: '',
		type: 'fermenter',
		brand: '',
		model: '',
		capacity_liters: undefined,
		is_active: true,
		notes: ''
	});

	// Hop state
	let hops = $state<HopInventoryResponse[]>([]);
	let hopSummary = $state<HopSummary | null>(null);
	let showHopModal = $state(false);
	let editingHop = $state<HopInventoryResponse | null>(null);
	let newHop = $state<HopInventoryCreate>({
		variety: '',
		amount_grams: 0,
		alpha_acid_percent: undefined,
		crop_year: new Date().getFullYear(),
		form: 'pellet',
		storage_location: '',
		notes: ''
	});
	let hopSearchQuery = $state('');

	// Hop variety database
	let hopVarieties = $state<HopVarietyResponse[]>([]);

	// Hop variety search/select state
	let varietySearchInput = $state('');
	let showVarietyDropdown = $state(false);
	let highlightedVarietyIndex = $state(-1);
	let selectedVariety = $state<HopVarietyResponse | null>(null);

	// Fuzzy search for hop varieties
	let searchedVarieties = $derived.by(() => {
		if (!varietySearchInput.trim()) return hopVarieties.slice(0, 50);
		const query = varietySearchInput.toLowerCase();
		const terms = query.split(/\s+/).filter(Boolean);

		return hopVarieties
			.map(variety => {
				const searchText = `${variety.name} ${variety.origin || ''} ${variety.aroma_profile || ''}`.toLowerCase();
				let score = 0;
				for (const term of terms) {
					if (searchText.includes(term)) {
						score += 10;
						if (variety.name.toLowerCase().startsWith(term)) score += 5;
					}
				}
				return { variety, score };
			})
			.filter(item => item.score > 0)
			.sort((a, b) => b.score - a.score)
			.slice(0, 30)
			.map(item => item.variety);
	});

	// Yeast state
	let yeasts = $state<YeastInventoryResponse[]>([]);
	let yeastSummary = $state<YeastInventorySummary | null>(null);
	let expiringYeasts = $state<YeastInventoryResponse[]>([]);
	let showYeastModal = $state(false);
	let editingYeast = $state<YeastInventoryResponse | null>(null);
	let newYeast = $state<YeastInventoryCreate>({
		yeast_strain_id: undefined,
		custom_name: '',
		quantity: 1,
		form: 'dry',
		expiry_date: '',
		storage_location: '',
		notes: ''
	});
	let yeastStrains = $state<YeastStrainResponse[]>([]);
	let yeastSearchQuery = $state('');
	let includeExpired = $state(false);

	// Yeast strain search/select state
	let strainSearchInput = $state('');
	let showStrainDropdown = $state(false);
	let highlightedStrainIndex = $state(-1);
	let selectedStrain = $state<YeastStrainResponse | null>(null);

	// Fuzzy search for yeast strains
	let searchedStrains = $derived.by(() => {
		if (!strainSearchInput.trim()) return yeastStrains.slice(0, 50);
		const query = strainSearchInput.toLowerCase();
		const terms = query.split(/\s+/).filter(Boolean);

		return yeastStrains
			.map(strain => {
				const searchText = `${strain.name} ${strain.producer} ${strain.product_id || ''}`.toLowerCase();
				// Score based on how many terms match and position
				let score = 0;
				for (const term of terms) {
					if (searchText.includes(term)) {
						score += 10;
						// Bonus for exact start match
						if (strain.name.toLowerCase().startsWith(term)) score += 5;
						if (strain.product_id?.toLowerCase().startsWith(term)) score += 5;
					}
				}
				return { strain, score };
			})
			.filter(item => item.score > 0)
			.sort((a, b) => b.score - a.score)
			.slice(0, 30)
			.map(item => item.strain);
	});

	// Adjust modal state
	let showAdjustModal = $state(false);
	let adjustingHop = $state<HopInventoryResponse | null>(null);
	let adjustAmount = $state(0);

	// Delete confirmation
	let deleteTarget = $state<{ type: 'equipment' | 'hop' | 'yeast'; item: any } | null>(null);

	let saving = $state(false);
	let deleting = $state(false);

	// Equipment types for dropdown
	const equipmentTypes: { value: EquipmentType; label: string }[] = [
		{ value: 'all_in_one', label: 'All-in-One System' },
		{ value: 'kettle', label: 'Brew Kettle' },
		{ value: 'fermenter', label: 'Fermenter' },
		{ value: 'mash_tun', label: 'Mash Tun' },
		{ value: 'lauter_tun', label: 'Lauter Tun' },
		{ value: 'hot_liquor_tank', label: 'Hot Liquor Tank' },
		{ value: 'chiller', label: 'Chiller' },
		{ value: 'pump', label: 'Pump' },
		{ value: 'mill', label: 'Grain Mill' },
		{ value: 'bottling', label: 'Bottling' },
		{ value: 'kegging', label: 'Kegging' },
		{ value: 'other', label: 'Other' }
	];

	// Filtered lists
	let filteredHops = $derived.by(() => {
		if (!hopSearchQuery) return hops;
		const q = hopSearchQuery.toLowerCase();
		return hops.filter(
			(h) =>
				h.variety.toLowerCase().includes(q) ||
				h.storage_location?.toLowerCase().includes(q) ||
				h.supplier?.toLowerCase().includes(q)
		);
	});

	let filteredYeasts = $derived.by(() => {
		if (!yeastSearchQuery) return yeasts;
		const q = yeastSearchQuery.toLowerCase();
		return yeasts.filter(
			(y) =>
				y.yeast_strain?.name.toLowerCase().includes(q) ||
				y.custom_name?.toLowerCase().includes(q) ||
				y.yeast_strain?.product_id?.toLowerCase().includes(q)
		);
	});

	async function loadData() {
		loading = true;
		error = null;
		try {
			const [equipData, hopData, hopSumData, yeastData, yeastSumData, expiringData, strainsData, varietiesData] =
				await Promise.all([
					fetchEquipment(),
					fetchHopInventory(),
					fetchHopSummary(),
					fetchYeastInventory({ include_expired: includeExpired }),
					fetchYeastInventorySummary(),
					fetchExpiringYeast(30),
					fetchYeastStrains({ limit: 500 }),
					fetchHopVarieties({ limit: 500 })
				]);
			equipment = equipData;
			hops = hopData;
			hopSummary = hopSumData;
			yeasts = yeastData;
			yeastSummary = yeastSumData;
			expiringYeasts = expiringData;
			yeastStrains = strainsData;
			hopVarieties = varietiesData;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load inventory';
		} finally {
			loading = false;
		}
	}

	// Equipment handlers
	function openEquipmentModal(item?: EquipmentResponse) {
		if (item) {
			editingEquipment = item;
			newEquipment = {
				name: item.name,
				type: item.type,
				brand: item.brand || '',
				model: item.model || '',
				capacity_liters: item.capacity_liters,
				is_active: item.is_active,
				notes: item.notes || ''
			};
		} else {
			editingEquipment = null;
			newEquipment = {
				name: '',
				type: 'fermenter',
				brand: '',
				model: '',
				capacity_liters: undefined,
				is_active: true,
				notes: ''
			};
		}
		showEquipmentModal = true;
	}

	async function handleSaveEquipment() {
		if (!newEquipment.name.trim()) return;
		saving = true;
		try {
			if (editingEquipment) {
				const updated = await updateEquipment(editingEquipment.id, newEquipment);
				equipment = equipment.map((e) => (e.id === updated.id ? updated : e));
			} else {
				const created = await createEquipment(newEquipment);
				equipment = [created, ...equipment];
			}
			showEquipmentModal = false;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save equipment';
		} finally {
			saving = false;
		}
	}

	// Hop handlers
	function openHopModal(item?: HopInventoryResponse) {
		if (item) {
			editingHop = item;
			newHop = {
				variety: item.variety,
				amount_grams: item.amount_grams,
				alpha_acid_percent: item.alpha_acid_percent,
				crop_year: item.crop_year,
				form: item.form,
				storage_location: item.storage_location || '',
				supplier: item.supplier || '',
				notes: item.notes || ''
			};
			// Find matching variety from database
			selectedVariety = hopVarieties.find(v => v.name.toLowerCase() === item.variety.toLowerCase()) || null;
			varietySearchInput = item.variety;
		} else {
			editingHop = null;
			newHop = {
				variety: '',
				amount_grams: 0,
				alpha_acid_percent: undefined,
				crop_year: new Date().getFullYear(),
				form: 'pellet',
				storage_location: '',
				notes: ''
			};
			selectedVariety = null;
			varietySearchInput = '';
		}
		showVarietyDropdown = false;
		highlightedVarietyIndex = -1;
		showHopModal = true;
	}

	function selectHopVariety(variety: HopVarietyResponse | null) {
		selectedVariety = variety;
		if (variety) {
			newHop.variety = variety.name;
			varietySearchInput = variety.name;
			// Auto-fill alpha acid if available
			if (variety.alpha_acid_low && variety.alpha_acid_high) {
				newHop.alpha_acid_percent = (variety.alpha_acid_low + variety.alpha_acid_high) / 2;
			}
		} else {
			newHop.variety = '';
			varietySearchInput = '';
		}
		showVarietyDropdown = false;
		highlightedVarietyIndex = -1;
	}

	function handleVarietyKeydown(e: KeyboardEvent) {
		const varieties = searchedVarieties;
		if (!showVarietyDropdown && e.key !== 'Escape') {
			showVarietyDropdown = true;
			return;
		}

		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				highlightedVarietyIndex = Math.min(highlightedVarietyIndex + 1, varieties.length - 1);
				break;
			case 'ArrowUp':
				e.preventDefault();
				highlightedVarietyIndex = Math.max(highlightedVarietyIndex - 1, -1);
				break;
			case 'Enter':
				e.preventDefault();
				if (highlightedVarietyIndex >= 0 && highlightedVarietyIndex < varieties.length) {
					selectHopVariety(varieties[highlightedVarietyIndex]);
				} else if (varietySearchInput.trim()) {
					// Allow custom variety name
					newHop.variety = varietySearchInput.trim();
					showVarietyDropdown = false;
				}
				break;
			case 'Escape':
				showVarietyDropdown = false;
				highlightedVarietyIndex = -1;
				break;
			case 'Tab':
				showVarietyDropdown = false;
				break;
		}
	}

	function handleVarietyInput() {
		showVarietyDropdown = true;
		highlightedVarietyIndex = -1;
		// Update variety name as user types (allows custom names)
		newHop.variety = varietySearchInput;
		// Clear selection if user is typing something different
		if (selectedVariety && varietySearchInput !== selectedVariety.name) {
			selectedVariety = null;
		}
	}

	async function handleSaveHop() {
		if (!newHop.variety.trim()) return;
		saving = true;
		try {
			if (editingHop) {
				const updated = await updateHopInventory(editingHop.id, newHop);
				hops = hops.map((h) => (h.id === updated.id ? updated : h));
			} else {
				const created = await createHopInventory(newHop);
				hops = [created, ...hops];
			}
			showHopModal = false;
			// Refresh summary
			hopSummary = await fetchHopSummary();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save hop';
		} finally {
			saving = false;
		}
	}

	function openAdjustModal(hop: HopInventoryResponse) {
		adjustingHop = hop;
		adjustAmount = 0;
		showAdjustModal = true;
	}

	async function handleAdjustHop() {
		if (!adjustingHop || adjustAmount === 0) return;
		saving = true;
		try {
			const updated = await adjustHopAmount(adjustingHop.id, adjustAmount);
			hops = hops.map((h) => (h.id === updated.id ? updated : h));
			showAdjustModal = false;
			hopSummary = await fetchHopSummary();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to adjust hop amount';
		} finally {
			saving = false;
		}
	}

	// Yeast handlers
	function openYeastModal(item?: YeastInventoryResponse) {
		if (item) {
			editingYeast = item;
			newYeast = {
				yeast_strain_id: item.yeast_strain_id,
				custom_name: item.custom_name || '',
				quantity: item.quantity,
				form: item.form,
				expiry_date: item.expiry_date?.split('T')[0] || '',
				storage_location: item.storage_location || '',
				supplier: item.supplier || '',
				notes: item.notes || ''
			};
			// Set the selected strain for editing
			if (item.yeast_strain_id) {
				selectedStrain = yeastStrains.find(s => s.id === item.yeast_strain_id) || null;
				strainSearchInput = selectedStrain ? `${selectedStrain.name} (${selectedStrain.producer})` : '';
			} else {
				selectedStrain = null;
				strainSearchInput = '';
			}
		} else {
			editingYeast = null;
			newYeast = {
				yeast_strain_id: undefined,
				custom_name: '',
				quantity: 1,
				form: 'dry',
				expiry_date: '',
				storage_location: '',
				notes: ''
			};
			selectedStrain = null;
			strainSearchInput = '';
		}
		showStrainDropdown = false;
		highlightedStrainIndex = -1;
		showYeastModal = true;
	}

	function selectYeastStrain(strain: YeastStrainResponse | null) {
		selectedStrain = strain;
		if (strain) {
			newYeast.yeast_strain_id = strain.id;
			strainSearchInput = `${strain.name} (${strain.producer})`;
		} else {
			newYeast.yeast_strain_id = undefined;
			strainSearchInput = '';
		}
		showStrainDropdown = false;
		highlightedStrainIndex = -1;
	}

	function handleStrainKeydown(e: KeyboardEvent) {
		const strains = searchedStrains;
		if (!showStrainDropdown && e.key !== 'Escape') {
			showStrainDropdown = true;
			return;
		}

		switch (e.key) {
			case 'ArrowDown':
				e.preventDefault();
				highlightedStrainIndex = Math.min(highlightedStrainIndex + 1, strains.length - 1);
				break;
			case 'ArrowUp':
				e.preventDefault();
				highlightedStrainIndex = Math.max(highlightedStrainIndex - 1, -1);
				break;
			case 'Enter':
				e.preventDefault();
				if (highlightedStrainIndex >= 0 && highlightedStrainIndex < strains.length) {
					selectYeastStrain(strains[highlightedStrainIndex]);
				}
				break;
			case 'Escape':
				showStrainDropdown = false;
				highlightedStrainIndex = -1;
				break;
			case 'Tab':
				showStrainDropdown = false;
				break;
		}
	}

	function handleStrainInput() {
		showStrainDropdown = true;
		highlightedStrainIndex = -1;
		// Clear selection if user is typing something different
		if (selectedStrain) {
			const currentDisplay = `${selectedStrain.name} (${selectedStrain.producer})`;
			if (strainSearchInput !== currentDisplay) {
				selectedStrain = null;
				newYeast.yeast_strain_id = undefined;
			}
		}
	}

	async function handleSaveYeast() {
		if (!newYeast.yeast_strain_id && !newYeast.custom_name?.trim()) {
			error = 'Select a yeast strain or enter a custom name';
			return;
		}
		saving = true;
		try {
			const payload = {
				...newYeast,
				expiry_date: newYeast.expiry_date || undefined
			};
			if (editingYeast) {
				const updated = await updateYeastInventory(editingYeast.id, payload);
				yeasts = yeasts.map((y) => (y.id === updated.id ? updated : y));
			} else {
				const created = await createYeastInventory(payload);
				yeasts = [created, ...yeasts];
			}
			showYeastModal = false;
			yeastSummary = await fetchYeastInventorySummary();
			expiringYeasts = await fetchExpiringYeast(30);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to save yeast';
		} finally {
			saving = false;
		}
	}

	async function handleUseYeast(yeast: YeastInventoryResponse) {
		try {
			const updated = await useYeast(yeast.id, 1);
			yeasts = yeasts.map((y) => (y.id === updated.id ? updated : y));
			yeastSummary = await fetchYeastInventorySummary();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to use yeast';
		}
	}

	// Delete handler
	async function handleDelete() {
		if (!deleteTarget) return;
		deleting = true;
		try {
			if (deleteTarget.type === 'equipment') {
				await deleteEquipment(deleteTarget.item.id);
				equipment = equipment.filter((e) => e.id !== deleteTarget!.item.id);
			} else if (deleteTarget.type === 'hop') {
				await deleteHopInventory(deleteTarget.item.id);
				hops = hops.filter((h) => h.id !== deleteTarget!.item.id);
				hopSummary = await fetchHopSummary();
			} else if (deleteTarget.type === 'yeast') {
				await deleteYeastInventory(deleteTarget.item.id);
				yeasts = yeasts.filter((y) => y.id !== deleteTarget!.item.id);
				yeastSummary = await fetchYeastInventorySummary();
			}
			deleteTarget = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to delete item';
		} finally {
			deleting = false;
		}
	}

	function formatDate(dateStr?: string): string {
		if (!dateStr) return '--';
		return new Date(dateStr).toLocaleDateString();
	}

	function getDaysUntilExpiry(dateStr?: string): number | null {
		if (!dateStr) return null;
		const expiry = new Date(dateStr);
		const now = new Date();
		const diff = expiry.getTime() - now.getTime();
		return Math.ceil(diff / (1000 * 60 * 60 * 24));
	}

	function getExpiryClass(dateStr?: string): string {
		const days = getDaysUntilExpiry(dateStr);
		if (days === null) return '';
		if (days < 0) return 'exp-past';
		if (days <= 30) return 'exp-soon';
		return 'exp-ok';
	}

	onMount(loadData);
</script>

<div class="inv">
	<header class="page-head">
		<h1 class="page-title">Inventory</h1>
		<p class="page-desc">Equipment, hops and yeast on hand</p>
	</header>

	{#if error}
		<div class="alert" role="alert">
			<span><strong>Error</strong> {error}</span>
			<button onclick={() => (error = null)} class="link-btn">Dismiss</button>
		</div>
	{/if}

	<div class="tabs" role="tablist">
		<button role="tab" aria-selected={activeTab === 'equipment'} class="tab" class:active={activeTab === 'equipment'} onclick={() => (activeTab = 'equipment')}>
			Equipment <span class="count">{equipment.length}</span>
		</button>
		<button role="tab" aria-selected={activeTab === 'hops'} class="tab" class:active={activeTab === 'hops'} onclick={() => (activeTab = 'hops')}>
			Hops <span class="count">{hops.length}</span>
		</button>
		<button role="tab" aria-selected={activeTab === 'yeast'} class="tab" class:active={activeTab === 'yeast'} onclick={() => (activeTab = 'yeast')}>
			Yeast <span class="count">{yeasts.length}</span>
			{#if yeastSummary && yeastSummary.expiring_soon > 0}
				<span class="pill warn">{yeastSummary.expiring_soon} expiring</span>
			{/if}
		</button>
	</div>

	{#if loading}
		<p class="empty" role="status">Loading inventory...</p>
	{:else}
		{#if activeTab === 'equipment'}
			<section class="panel">
				<div class="toolbar">
					<p class="meta"><span class="num">{equipment.length}</span> items</p>
					<button onclick={() => openEquipmentModal()} class="btn-primary">Add Equipment</button>
				</div>

				{#if equipment.length === 0}
					<div class="empty">
						<p>No equipment added yet</p>
						<button onclick={() => openEquipmentModal()} class="link-btn accent empty-link">Add your first equipment</button>
					</div>
				{:else}
					<div class="scroll">
						<table class="ledger">
							<thead>
								<tr>
									<th>Name</th>
									<th>Type</th>
									<th>Make / model</th>
									<th class="r">Capacity</th>
									<th>Status</th>
									<th class="r">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#each equipment as item}
									<tr>
										<td data-label="Name" class="strong name">
											{item.name}
											<span class="rowmeta">{equipmentTypes.find((t) => t.value === item.type)?.label || item.type}{[item.brand, item.model].filter(Boolean).length ? ' \u00b7 ' + [item.brand, item.model].filter(Boolean).join(' ') : ''}</span>
										</td>
										<td data-label="Type" class="muted hide-phone">{equipmentTypes.find((t) => t.value === item.type)?.label || item.type}</td>
										<td data-label="Make / model" class="muted hide-phone">{[item.brand, item.model].filter(Boolean).join(' ') || '--'}</td>
										<td data-label="Capacity" class="r num v1"><span class="lbl">Capacity</span>{item.capacity_liters ? `${item.capacity_liters}\u2009L` : '--'}</td>
										<td data-label="Status" class="v2"><span class="lbl">Status</span><span class="pill" class:steady={item.is_active}>{item.is_active ? 'Active' : 'Inactive'}</span></td>
										<td class="r actions">
											<button onclick={() => openEquipmentModal(item)} class="link-btn">Edit</button>
											<button onclick={() => (deleteTarget = { type: 'equipment', item })} class="link-btn danger">Delete</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
		{/if}

		{#if activeTab === 'hops'}
			<section class="panel">
				{#if hopSummary}
					<div class="strip">
						<div class="cell">
							<span class="label">Total weight</span>
							<span class="value num">{(hopSummary.total_grams / 1000).toFixed(2)}<span class="unit">&thinsp;kg</span></span>
						</div>
						<div class="cell">
							<span class="label">Varieties</span>
							<span class="value num">{hopSummary.unique_varieties}</span>
						</div>
						<div class="cell">
							<span class="label">Lots</span>
							<span class="value num">{hopSummary.total_items}</span>
						</div>
					</div>
				{/if}

				<div class="toolbar">
					<input type="text" placeholder="Search hops..." aria-label="Search hops" bind:value={hopSearchQuery} class="field search" />
					<button onclick={() => openHopModal()} class="btn-primary">Add Hops</button>
				</div>

				{#if filteredHops.length === 0}
					<div class="empty"><p>{hopSearchQuery ? 'No hops match your search' : 'No hops in inventory'}</p></div>
				{:else}
					<div class="scroll">
						<table class="ledger">
							<thead>
								<tr>
									<th>Variety</th>
									<th class="r">Amount</th>
									<th class="r">AA%</th>
									<th class="pl">Form</th>
									<th>Year</th>
									<th>Location</th>
									<th class="r">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#each filteredHops as hop}
									<tr>
										<td data-label="Variety" class="strong name">
											{hop.variety}
											<span class="rowmeta cap">{hop.form}{hop.crop_year ? ' \u00b7 ' + hop.crop_year : ''}{hop.storage_location ? ' \u00b7 ' + hop.storage_location : ''}</span>
										</td>
										<td data-label="Amount" class="r num v1">
											<span class="lbl">Amount</span>
											{#if hop.amount_grams < 50}<span class="pill warn">Low</span>{/if}
											{hop.amount_grams >= 1000
												? `${(hop.amount_grams / 1000).toFixed(2)}\u2009kg`
												: `${hop.amount_grams.toFixed(0)}\u2009g`}
										</td>
										<td data-label="AA%" class="r num v2"><span class="lbl">Alpha acid</span>{hop.alpha_acid_percent?.toFixed(1) || '--'}{#if hop.alpha_acid_percent}<span class="pu">&thinsp;AA%</span>{/if}</td>
										<td data-label="Form" class="pl small muted cap hide-phone">{hop.form}</td>
										<td data-label="Year" class="small muted num hide-phone">{hop.crop_year || '--'}</td>
										<td data-label="Location" class="small muted hide-phone">{hop.storage_location || '--'}</td>
										<td class="r actions">
											<button onclick={() => openAdjustModal(hop)} class="link-btn accent">Adjust</button>
											<button onclick={() => openHopModal(hop)} class="link-btn">Edit</button>
											<button onclick={() => (deleteTarget = { type: 'hop', item: hop })} class="link-btn danger">Delete</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
		{/if}

		{#if activeTab === 'yeast'}
			<section class="panel">
				{#if yeastSummary}
					<div class="strip four">
						<div class="cell">
							<span class="label">Total packs</span>
							<span class="value num">{yeastSummary.total_quantity}</span>
						</div>
						<div class="cell">
							<span class="label">Strains</span>
							<span class="value num">{yeastSummary.total_items}</span>
						</div>
						<div class="cell">
							<span class="label">Expiring soon</span>
							<span class="value num" class:warn-text={yeastSummary.expiring_soon > 0}>{yeastSummary.expiring_soon}</span>
						</div>
						<div class="cell">
							<span class="label">Expired</span>
							<span class="value num" class:danger-text={yeastSummary.expired > 0}>{yeastSummary.expired}</span>
						</div>
					</div>
				{/if}

				{#if expiringYeasts.length > 0}
					<div class="notice">
						<p class="notice-title"><span class="pill warn">Expiring</span> Yeast expiring within 30 days</p>
						<ul>
							{#each expiringYeasts.slice(0, 5) as yeast}
								<li>{yeast.yeast_strain?.name || yeast.custom_name} <span class="muted">expires</span> <span class="num">{formatDate(yeast.expiry_date)}</span></li>
							{/each}
							{#if expiringYeasts.length > 5}
								<li class="muted">...and {expiringYeasts.length - 5} more</li>
							{/if}
						</ul>
					</div>
				{/if}

				<div class="toolbar">
					<div class="toolbar-left">
						<input type="text" placeholder="Search yeast..." aria-label="Search yeast" bind:value={yeastSearchQuery} class="field search" />
						<label class="check">
							<input type="checkbox" bind:checked={includeExpired} onchange={loadData} />
							Show expired
						</label>
					</div>
					<button onclick={() => openYeastModal()} class="btn-primary">Add Yeast</button>
				</div>

				{#if filteredYeasts.length === 0}
					<div class="empty"><p>{yeastSearchQuery ? 'No yeast matches your search' : 'No yeast in inventory'}</p></div>
				{:else}
					<div class="scroll">
						<table class="ledger">
							<thead>
								<tr>
									<th>Strain</th>
									<th class="r">Qty</th>
									<th class="pl">Form</th>
									<th>Expiry</th>
									<th>Location</th>
									<th class="r">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#each filteredYeasts as yeast}
									<tr>
										<td data-label="Strain" class="name">
											<div class="strong">{yeast.yeast_strain?.name || yeast.custom_name}</div>
											{#if yeast.yeast_strain?.product_id}
												<div class="small muted">{yeast.yeast_strain.producer} - {yeast.yeast_strain.product_id}</div>
											{/if}
											{#if yeast.generation}
												<div class="small muted">Gen <span class="num">{yeast.generation}</span> (harvested)</div>
											{/if}
											<span class="rowmeta cap">{yeast.form}{yeast.storage_location ? ' \u00b7 ' + yeast.storage_location : ''}</span>
										</td>
										<td data-label="Qty" class="r num v1"><span class="lbl">Quantity</span>{yeast.quantity}<span class="pu">&thinsp;pk</span></td>
										<td data-label="Form" class="pl small muted cap hide-phone">{yeast.form}</td>
										<td data-label="Expiry" class="num v2 {getExpiryClass(yeast.expiry_date)}">
											<span class="lbl">Expiry</span>
											{formatDate(yeast.expiry_date)}
											{#if getDaysUntilExpiry(yeast.expiry_date) !== null}
												<span class="small">({getDaysUntilExpiry(yeast.expiry_date)}&thinsp;d)</span>
											{/if}
										</td>
										<td data-label="Location" class="small muted hide-phone">{yeast.storage_location || '--'}</td>
										<td class="r actions">
											{#if yeast.quantity > 0}
												<button onclick={() => handleUseYeast(yeast)} class="link-btn accent">Use 1</button>
											{/if}
											<button onclick={() => openYeastModal(yeast)} class="link-btn">Edit</button>
											<button onclick={() => (deleteTarget = { type: 'yeast', item: yeast })} class="link-btn danger">Delete</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</section>
		{/if}
	{/if}
</div>

<!-- Equipment Modal -->
{#if showEquipmentModal}
	<div class="scrim">
		<div class="modal" role="dialog" aria-modal="true" aria-label={editingEquipment ? 'Edit Equipment' : 'Add Equipment'}>
			<h2 class="modal-title">{editingEquipment ? 'Edit Equipment' : 'Add Equipment'}</h2>
			<div class="form">
				<div>
					<label class="flabel">Name *</label>
					<input type="text" bind:value={newEquipment.name} class="field" placeholder="My Fermenter" />
				</div>
				<div>
					<label class="flabel">Type *</label>
					<select bind:value={newEquipment.type} class="field">
						{#each equipmentTypes as type}
							<option value={type.value}>{type.label}</option>
						{/each}
					</select>
				</div>
				<div class="two">
					<div>
						<label class="flabel">Brand</label>
						<input type="text" bind:value={newEquipment.brand} class="field" />
					</div>
					<div>
						<label class="flabel">Model</label>
						<input type="text" bind:value={newEquipment.model} class="field" />
					</div>
				</div>
				<div>
					<label class="flabel">Capacity (L)</label>
					<input type="number" step="0.1" bind:value={newEquipment.capacity_liters} class="field" />
				</div>
				<div>
					<label class="flabel">Notes</label>
					<textarea bind:value={newEquipment.notes} rows="2" class="field area"></textarea>
				</div>
				<label class="check">
					<input type="checkbox" bind:checked={newEquipment.is_active} />
					Active
				</label>
			</div>
			<div class="modal-actions">
				<button onclick={() => (showEquipmentModal = false)} class="btn-secondary">Cancel</button>
				<button onclick={handleSaveEquipment} disabled={saving || !newEquipment.name.trim()} class="btn-primary">
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Hop Modal -->
{#if showHopModal}
	<div class="scrim">
		<div class="modal" role="dialog" aria-modal="true" aria-label={editingHop ? 'Edit Hop' : 'Add Hop'}>
			<h2 class="modal-title">{editingHop ? 'Edit Hop' : 'Add Hop'}</h2>
			<div class="form">
				<div class="rel">
					<label class="flabel">Variety *</label>
					<div class="rel">
						<input
							type="text"
							bind:value={varietySearchInput}
							oninput={handleVarietyInput}
							onkeydown={handleVarietyKeydown}
							onfocus={() => (showVarietyDropdown = true)}
							onblur={() => setTimeout(() => (showVarietyDropdown = false), 200)}
							placeholder="Search by name or origin..."
							class="field has-clear"
						/>
						{#if selectedVariety}
							<button type="button" onclick={() => selectHopVariety(null)} class="clear-btn" aria-label="Clear hop variety selection">
								<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
								</svg>
							</button>
						{/if}
					</div>
					{#if showVarietyDropdown && searchedVarieties.length > 0}
						<div class="dropdown">
							{#each searchedVarieties as variety, i}
								<button
									type="button"
									class="option"
									class:hl={highlightedVarietyIndex === i}
									onmouseenter={() => (highlightedVarietyIndex = i)}
									onmousedown={() => selectHopVariety(variety)}
								>
									<div class="strong">{variety.name}</div>
									<div class="small muted">{variety.origin} &middot; Alpha <span class="num">{variety.alpha_acid_low}-{variety.alpha_acid_high}%</span></div>
								</button>
							{/each}
						</div>
					{:else if showVarietyDropdown && varietySearchInput.trim() && searchedVarieties.length === 0}
						<div class="dropdown pad muted">No matching varieties found. Enter custom name.</div>
					{/if}
				</div>
				<div class="two">
					<div>
						<label class="flabel">Amount (g) *</label>
						<input type="number" step="1" bind:value={newHop.amount_grams} class="field" />
					</div>
					<div>
						<label class="flabel">Alpha Acid %</label>
						<input type="number" step="0.1" bind:value={newHop.alpha_acid_percent} class="field" />
					</div>
				</div>
				<div class="two">
					<div>
						<label class="flabel">Form</label>
						<select bind:value={newHop.form} class="field">
							<option value="pellet">Pellet</option>
							<option value="leaf">Leaf</option>
							<option value="plug">Plug</option>
						</select>
					</div>
					<div>
						<label class="flabel">Crop Year</label>
						<input type="number" bind:value={newHop.crop_year} class="field" />
					</div>
				</div>
				<div>
					<label class="flabel">Storage Location</label>
					<input type="text" bind:value={newHop.storage_location} class="field" placeholder="Freezer A" />
				</div>
				<div>
					<label class="flabel">Notes</label>
					<textarea bind:value={newHop.notes} rows="2" class="field area"></textarea>
				</div>
			</div>
			<div class="modal-actions">
				<button onclick={() => (showHopModal = false)} class="btn-secondary">Cancel</button>
				<button onclick={handleSaveHop} disabled={saving || !newHop.variety.trim()} class="btn-primary">
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Adjust Hop Amount Modal -->
{#if showAdjustModal && adjustingHop}
	<div class="scrim">
		<div class="modal narrow" role="dialog" aria-modal="true" aria-label="Adjust {adjustingHop.variety}">
			<h2 class="modal-title">Adjust {adjustingHop.variety}</h2>
			<p class="meta">Current: <span class="num">{adjustingHop.amount_grams}&thinsp;g</span></p>
			<div class="form">
				<div>
					<label class="flabel">Amount to add/subtract (g)</label>
					<input type="number" bind:value={adjustAmount} class="field" placeholder="-50 or 100" />
					<p class="hint">Use negative numbers to subtract</p>
				</div>
			</div>
			<div class="modal-actions">
				<button onclick={() => (showAdjustModal = false)} class="btn-secondary">Cancel</button>
				<button onclick={handleAdjustHop} disabled={saving || adjustAmount === 0} class="btn-primary">
					{saving ? 'Adjusting...' : 'Adjust'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Yeast Modal -->
{#if showYeastModal}
	<div class="scrim">
		<div class="modal" role="dialog" aria-modal="true" aria-label={editingYeast ? 'Edit Yeast' : 'Add Yeast'}>
			<h2 class="modal-title">{editingYeast ? 'Edit Yeast' : 'Add Yeast'}</h2>
			<div class="form">
				<div class="rel">
					<label class="flabel">Yeast Strain</label>
					<div class="rel">
						<input
							type="text"
							bind:value={strainSearchInput}
							oninput={handleStrainInput}
							onkeydown={handleStrainKeydown}
							onfocus={() => (showStrainDropdown = true)}
							onblur={() => setTimeout(() => (showStrainDropdown = false), 200)}
							placeholder="Search by name, producer, or product ID..."
							class="field has-clear"
						/>
						{#if selectedStrain}
							<button type="button" onclick={() => selectYeastStrain(null)} class="clear-btn" aria-label="Clear yeast strain selection">
								<svg width="14" height="14" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
									<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
								</svg>
							</button>
						{/if}
					</div>
					{#if showStrainDropdown && searchedStrains.length > 0}
						<div class="dropdown">
							{#each searchedStrains as strain, i}
								<button
									type="button"
									class="option"
									class:hl={highlightedStrainIndex === i}
									onmouseenter={() => (highlightedStrainIndex = i)}
									onmousedown={() => selectYeastStrain(strain)}
								>
									<div class="strong">{strain.name}</div>
									<div class="small muted">{strain.producer} {strain.product_id ? `- ${strain.product_id}` : ''}</div>
								</button>
							{/each}
						</div>
					{:else if showStrainDropdown && strainSearchInput.trim() && searchedStrains.length === 0}
						<div class="dropdown pad muted">No matching strains found. Use "Custom Name" below.</div>
					{/if}
				</div>
				{#if !newYeast.yeast_strain_id}
					<div>
						<label class="flabel">Custom Name</label>
						<input type="text" bind:value={newYeast.custom_name} class="field" placeholder="My harvested strain" />
					</div>
				{/if}
				<div class="two">
					<div>
						<label class="flabel">Quantity</label>
						<input type="number" min="0" bind:value={newYeast.quantity} class="field" />
					</div>
					<div>
						<label class="flabel">Form</label>
						<select bind:value={newYeast.form} class="field">
							<option value="dry">Dry</option>
							<option value="liquid">Liquid</option>
							<option value="slant">Slant</option>
							<option value="harvested">Harvested</option>
						</select>
					</div>
				</div>
				<div>
					<label class="flabel">Expiry Date</label>
					<input type="date" bind:value={newYeast.expiry_date} class="field" />
				</div>
				<div>
					<label class="flabel">Storage Location</label>
					<input type="text" bind:value={newYeast.storage_location} class="field" placeholder="Fridge A" />
				</div>
				<div>
					<label class="flabel">Notes</label>
					<textarea bind:value={newYeast.notes} rows="2" class="field area"></textarea>
				</div>
			</div>
			<div class="modal-actions">
				<button onclick={() => (showYeastModal = false)} class="btn-secondary">Cancel</button>
				<button onclick={handleSaveYeast} disabled={saving} class="btn-primary">
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<div class="scrim">
		<div class="modal narrow" role="alertdialog" aria-modal="true" aria-label="Confirm Delete">
			<h2 class="modal-title">Confirm Delete</h2>
			<p class="body-text">
				Are you sure you want to delete
				<strong>
					{#if deleteTarget.type === 'equipment'}
						{deleteTarget.item.name}
					{:else if deleteTarget.type === 'hop'}
						{deleteTarget.item.variety}
					{:else}
						{deleteTarget.item.yeast_strain?.name || deleteTarget.item.custom_name}
					{/if}
				</strong>?
			</p>
			<div class="modal-actions">
				<button onclick={() => (deleteTarget = null)} class="btn-secondary">Cancel</button>
				<button onclick={handleDelete} disabled={deleting} class="btn-danger">
					{deleting ? 'Deleting...' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}

<style>
	.inv { display: flex; flex-direction: column; gap: var(--space-md); padding-bottom: var(--space-xl); }
	.page-title { font-family: var(--font-display); font-size: var(--text-xl); font-weight: 700; letter-spacing: -0.02em; line-height: 1.15; color: var(--ink-primary); }
	.page-desc { font-size: var(--text-sm); color: var(--ink-secondary); margin-top: var(--space-2xs); }
	.alert { display: flex; align-items: center; justify-content: space-between; gap: var(--space-md); padding: var(--space-sm) var(--space-md); border: 1px solid color-mix(in oklch, var(--status-danger) 60%, transparent); border-radius: 4px; color: var(--status-danger); font-size: var(--text-sm); }
	.tabs { display: flex; flex-wrap: nowrap; overflow-x: auto; overflow-y: hidden; scrollbar-width: none; box-shadow: inset 0 -1px 0 var(--rule-hairline); }
	.tabs::-webkit-scrollbar { display: none; }
	.tab { display: inline-flex; align-items: center; gap: var(--space-xs); min-height: 44px; padding: 0 var(--space-md); font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; color: var(--ink-secondary); border-bottom: 2px solid transparent; cursor: pointer; transition: color 140ms var(--ease-out-quart); white-space: nowrap; flex-shrink: 0; }
	.tab:hover { color: var(--ink-primary); }
	.tab.active { color: var(--accent); border-bottom-color: var(--accent); }
	.count { font-family: var(--font-num); font-variant-numeric: tabular-nums; font-size: var(--text-xs); color: var(--ink-muted); }
	.panel { display: flex; flex-direction: column; gap: var(--space-md); }
	.strip { display: grid; grid-template-columns: repeat(auto-fit, minmax(9rem, 1fr)); border: 1px solid var(--rule-strong); background: var(--bg-surface); border-radius: 4px; }
	.cell { display: flex; flex-direction: column; gap: var(--space-2xs); padding: var(--space-sm) var(--space-md); border-right: 1px solid var(--rule-hairline); }
	.cell:last-child { border-right: 0; }
	.label { font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); }
	.value { font-size: var(--text-lg); font-weight: 500; color: var(--ink-primary); line-height: 1.2; }
	.unit { font-size: var(--text-sm); color: var(--ink-secondary); }
	.num { font-family: var(--font-num); font-variant-numeric: tabular-nums; }
	.warn-text { color: var(--status-warn); }
	.danger-text { color: var(--status-danger); }
	.toolbar { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--space-sm); }
	.toolbar-left { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-md); flex: 1; }
	.meta { font-size: var(--text-sm); color: var(--ink-secondary); }
	.search { max-width: 20rem; flex: 1; min-width: 12rem; }
	.check { display: inline-flex; align-items: center; gap: var(--space-xs); min-height: 44px; font-size: var(--text-sm); color: var(--ink-secondary); }
	.check input { accent-color: var(--accent); width: 1rem; height: 1rem; }
	.field { width: 100%; min-height: 44px; padding: 0 var(--space-sm); font-size: var(--text-sm); color: var(--ink-primary); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; }
	.field::placeholder { color: var(--ink-muted); }
	.field:focus-visible { outline: 2px solid var(--accent); outline-offset: 1px; border-color: var(--accent); }
	.area { padding: var(--space-xs) var(--space-sm); min-height: 4.5rem; }
	.flabel { display: block; margin-bottom: var(--space-2xs); font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); }
	.hint { margin-top: var(--space-2xs); font-size: var(--text-xs); color: var(--ink-muted); }
	.btn-primary, .btn-secondary, .btn-danger { display: inline-flex; align-items: center; justify-content: center; min-height: 44px; padding: 0 var(--space-md); font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; border-radius: 4px; cursor: pointer; }
	.btn-primary { color: var(--accent-ink); background: var(--accent); }
	.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
	.btn-secondary { color: var(--ink-primary); background: var(--bg-surface); border: 1px solid var(--rule-strong); }
	.btn-secondary:hover { background: var(--accent-tint); border-color: var(--accent-rule); }
	.btn-danger { color: var(--status-danger); background: var(--bg-surface); border: 1px solid color-mix(in oklch, var(--status-danger) 55%, transparent); }
	.btn-danger:hover:not(:disabled) { background: var(--negative-muted); }
	:is(.btn-primary, .btn-danger):disabled { opacity: 0.5; cursor: not-allowed; }
	.btn-primary:focus-visible, .btn-secondary:focus-visible, .btn-danger:focus-visible, .link-btn:focus-visible, .tab:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.link-btn { min-height: 32px; padding: 0 var(--space-xs); font-family: var(--font-display); font-size: var(--text-sm); font-weight: 600; color: var(--ink-secondary); border-radius: 4px; cursor: pointer; }
	.link-btn:hover { color: var(--ink-primary); text-decoration: underline; }
	.link-btn.accent:hover, .link-btn.accent:focus-visible { color: var(--accent); }
	.link-btn.danger:hover, .link-btn.danger:focus-visible { color: var(--status-danger); }
	.link-btn.accent.empty-link { color: var(--accent); }
	.pill { display: inline-flex; align-items: center; padding: 1px var(--space-xs); font-family: var(--font-display); font-size: 0.6875rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); border: 1px solid var(--rule-strong); border-radius: 3px; line-height: 1.4; }
	.pill.warn { color: var(--status-warn); border-color: var(--status-warn); }
	.pill.steady { color: var(--status-steady); border-color: var(--status-steady); }
	.notice { padding: var(--space-sm) var(--space-md); border: 1px solid var(--rule-hairline); background: var(--bg-surface); border-radius: 4px; font-size: var(--text-sm); }
	.notice-title { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-xs); font-weight: 700; }
	.notice ul { margin-top: var(--space-xs); display: flex; flex-direction: column; gap: var(--space-2xs); }
	.empty { padding: var(--space-xl) var(--space-md); text-align: center; color: var(--ink-secondary); font-size: var(--text-sm); border-top: 1px solid var(--rule-hairline); border-bottom: 1px solid var(--rule-hairline); }
	.scroll { overflow-x: auto; position: relative; }
	.ledger { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
	.ledger th { padding: var(--space-xs) var(--space-sm); text-align: left; font-family: var(--font-display); font-size: var(--text-xs); font-weight: 600; text-transform: uppercase; letter-spacing: 0.07em; color: var(--ink-muted); border-bottom: 1px solid var(--rule-strong); white-space: nowrap; }
	.ledger td { padding: var(--space-sm); border-bottom: 1px solid var(--rule-hairline); color: var(--ink-primary); vertical-align: middle; }
	.ledger .r { text-align: right; }
	.ledger .pl { padding-left: var(--space-lg); }
	.ledger .actions { white-space: nowrap; }
	.strong { font-weight: 700; color: var(--ink-primary); }
	.ledger td.small { color: var(--ink-secondary); }
	.muted, .ledger td.muted { color: var(--ink-secondary); }
	.small { font-size: var(--text-xs); }
	.cap { text-transform: capitalize; }
	.ledger td.exp-past { color: var(--status-danger); }
	.ledger td.exp-soon { color: var(--status-warn); }
	.ledger td.exp-ok { color: var(--ink-secondary); }

	.scrim { position: fixed; inset: 0; z-index: 50; display: flex; align-items: center; justify-content: center; padding: var(--space-md); background: color-mix(in oklch, var(--bg-canvas) 75%, transparent); }
	.modal { width: 100%; max-width: 28rem; max-height: 92vh; overflow-y: auto; padding: var(--space-lg); background: var(--bg-surface); border: 1px solid var(--rule-strong); border-radius: 4px; }
	.modal.narrow { max-width: 24rem; }
	.modal-title { margin-bottom: var(--space-md); font-family: var(--font-display); font-size: var(--text-lg); font-weight: 700; color: var(--ink-primary); }
	.body-text { font-size: var(--text-sm); color: var(--ink-secondary); }
	.form { display: flex; flex-direction: column; gap: var(--space-md); }
	.two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-md); }
	.modal-actions { margin-top: var(--space-lg); display: flex; justify-content: flex-end; gap: var(--space-sm); }
	.rel { position: relative; }
	.has-clear { padding-right: 2.25rem; }
	.clear-btn { position: absolute; right: 2px; top: 50%; transform: translateY(-50%); display: inline-flex; align-items: center; justify-content: center; width: 40px; height: 40px; color: var(--ink-muted); cursor: pointer; }
	.clear-btn:hover { color: var(--ink-primary); }
	.dropdown { position: absolute; z-index: 10; margin-top: var(--space-2xs); width: 100%; max-height: 15rem; overflow: auto; background: var(--bg-elevated); border: 1px solid var(--rule-strong); border-radius: 4px; }
	.dropdown.pad { padding: var(--space-sm); font-size: var(--text-sm); }
	.option { display: block; width: 100%; min-height: 44px; padding: var(--space-xs) var(--space-sm); text-align: left; font-size: var(--text-sm); border-bottom: 1px solid var(--rule-hairline); cursor: pointer; }
	.option:hover, .option.hl { background: var(--accent-tint); }

	.lbl, .pu, .rowmeta { display: none; }
	@media (max-width: 640px) {
		.strip { grid-template-columns: repeat(3, 1fr); }
		.strip.four { grid-template-columns: repeat(2, 1fr); }
		.cell { padding: 10px 12px; }
		.strip.four .cell:nth-child(2n) { border-right: 0; }
		.strip.four .cell:nth-child(n + 3) { border-top: 1px solid var(--rule-hairline); }
		.tabs { padding-right: 28px; -webkit-mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 28px), transparent); mask-image: linear-gradient(to right, var(--ink-primary) calc(100% - 28px), transparent); }
		.search { max-width: none; }
		.two { grid-template-columns: 1fr; }
		.ledger thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
		.ledger, .ledger tbody { display: block; }
		.ledger tr { display: grid; grid-template-columns: 1fr auto; grid-template-areas: "name v1" "name v2" "act act"; gap: 4px 12px; padding: 12px 0; border-bottom: 1px solid var(--rule-hairline); }
		.ledger td { display: block; padding: 0; border: 0; text-align: left; }
		.ledger td.name { grid-area: name; }
		.ledger td.v1 { grid-area: v1; text-align: right; }
		.ledger td.v2 { grid-area: v2; text-align: right; font-size: var(--text-xs); }
		.ledger td.actions { grid-area: act; text-align: left; }
		.ledger td.hide-phone { display: none; }
		.rowmeta { display: block; font-weight: 400; font-size: var(--text-xs); color: var(--ink-secondary); }
		.pu { display: inline; color: var(--ink-muted); }
		.lbl { display: block; position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }
		.link-btn { min-height: 44px; padding: 0 var(--space-sm) 0 0; }
	}
</style>
