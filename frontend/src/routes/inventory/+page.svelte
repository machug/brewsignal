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
		fetchYeastStrains
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
	let filteredHops = $derived(() => {
		if (!hopSearchQuery) return hops;
		const q = hopSearchQuery.toLowerCase();
		return hops.filter(
			(h) =>
				h.variety.toLowerCase().includes(q) ||
				h.storage_location?.toLowerCase().includes(q) ||
				h.supplier?.toLowerCase().includes(q)
		);
	});

	let filteredYeasts = $derived(() => {
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
			const [equipData, hopData, hopSumData, yeastData, yeastSumData, expiringData, strainsData] =
				await Promise.all([
					fetchEquipment(),
					fetchHopInventory(),
					fetchHopSummary(),
					fetchYeastInventory({ include_expired: includeExpired }),
					fetchYeastInventorySummary(),
					fetchExpiringYeast(30),
					fetchYeastStrains({ limit: 500 })
				]);
			equipment = equipData;
			hops = hopData;
			hopSummary = hopSumData;
			yeasts = yeastData;
			yeastSummary = yeastSumData;
			expiringYeasts = expiringData;
			yeastStrains = strainsData;
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
		}
		showHopModal = true;
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
		}
		showYeastModal = true;
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
		if (days < 0) return 'text-red-500';
		if (days <= 30) return 'text-amber-500';
		return 'text-green-600';
	}

	onMount(loadData);
</script>

<div class="space-y-6">
	<!-- Header -->
	<div class="flex items-center justify-between">
		<div>
			<h1 class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">Inventory</h1>
			<p class="text-sm text-zinc-500 dark:text-zinc-400">
				Track your brewing equipment, hops, and yeast
			</p>
		</div>
	</div>

	<!-- Error display -->
	{#if error}
		<div class="rounded-lg bg-red-50 p-4 text-red-700 dark:bg-red-900/20 dark:text-red-400">
			{error}
			<button onclick={() => (error = null)} class="ml-2 underline">Dismiss</button>
		</div>
	{/if}

	<!-- Tabs -->
	<div class="border-b border-zinc-200 dark:border-zinc-700">
		<nav class="-mb-px flex space-x-8">
			<button
				onclick={() => (activeTab = 'equipment')}
				class="border-b-2 px-1 py-4 text-sm font-medium transition-colors {activeTab === 'equipment'
					? 'border-amber-500 text-amber-600 dark:text-amber-400'
					: 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'}"
			>
				Equipment
				<span
					class="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800"
				>
					{equipment.length}
				</span>
			</button>
			<button
				onclick={() => (activeTab = 'hops')}
				class="border-b-2 px-1 py-4 text-sm font-medium transition-colors {activeTab === 'hops'
					? 'border-amber-500 text-amber-600 dark:text-amber-400'
					: 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'}"
			>
				Hops
				<span
					class="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800"
				>
					{hops.length}
				</span>
			</button>
			<button
				onclick={() => (activeTab = 'yeast')}
				class="border-b-2 px-1 py-4 text-sm font-medium transition-colors {activeTab === 'yeast'
					? 'border-amber-500 text-amber-600 dark:text-amber-400'
					: 'border-transparent text-zinc-500 hover:border-zinc-300 hover:text-zinc-700 dark:text-zinc-400 dark:hover:text-zinc-300'}"
			>
				Yeast
				<span
					class="ml-2 rounded-full bg-zinc-100 px-2 py-0.5 text-xs dark:bg-zinc-800"
				>
					{yeasts.length}
				</span>
				{#if yeastSummary && yeastSummary.expiring_soon > 0}
					<span class="ml-1 rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
						{yeastSummary.expiring_soon} expiring
					</span>
				{/if}
			</button>
		</nav>
	</div>

	{#if loading}
		<div class="flex items-center justify-center py-12">
			<div class="h-8 w-8 animate-spin rounded-full border-4 border-amber-500 border-t-transparent"></div>
		</div>
	{:else}
		<!-- Equipment Tab -->
		{#if activeTab === 'equipment'}
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<p class="text-sm text-zinc-500 dark:text-zinc-400">
						{equipment.length} items
					</p>
					<button
						onclick={() => openEquipmentModal()}
						class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
					>
						Add Equipment
					</button>
				</div>

				{#if equipment.length === 0}
					<div class="rounded-lg border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-700">
						<p class="text-zinc-500 dark:text-zinc-400">No equipment added yet</p>
						<button
							onclick={() => openEquipmentModal()}
							class="mt-2 text-amber-600 hover:underline dark:text-amber-400"
						>
							Add your first equipment
						</button>
					</div>
				{:else}
					<div class="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
						{#each equipment as item}
							<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
								<div class="flex items-start justify-between">
									<div>
										<h3 class="font-medium text-zinc-900 dark:text-zinc-100">{item.name}</h3>
										<p class="text-sm text-zinc-500 dark:text-zinc-400">
											{equipmentTypes.find((t) => t.value === item.type)?.label || item.type}
										</p>
									</div>
									<span
										class="rounded-full px-2 py-0.5 text-xs {item.is_active
											? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
											: 'bg-zinc-100 text-zinc-500 dark:bg-zinc-700 dark:text-zinc-400'}"
									>
										{item.is_active ? 'Active' : 'Inactive'}
									</span>
								</div>
								{#if item.brand || item.model}
									<p class="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
										{[item.brand, item.model].filter(Boolean).join(' ')}
									</p>
								{/if}
								{#if item.capacity_liters}
									<p class="text-sm text-zinc-500 dark:text-zinc-400">
										{item.capacity_liters}L capacity
									</p>
								{/if}
								<div class="mt-3 flex gap-2">
									<button
										onclick={() => openEquipmentModal(item)}
										class="text-sm text-amber-600 hover:underline dark:text-amber-400"
									>
										Edit
									</button>
									<button
										onclick={() => (deleteTarget = { type: 'equipment', item })}
										class="text-sm text-red-600 hover:underline dark:text-red-400"
									>
										Delete
									</button>
								</div>
							</div>
						{/each}
					</div>
				{/if}
			</div>
		{/if}

		<!-- Hops Tab -->
		{#if activeTab === 'hops'}
			<div class="space-y-4">
				<!-- Summary cards -->
				{#if hopSummary}
					<div class="grid gap-4 sm:grid-cols-3">
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Total Weight</p>
							<p class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
								{(hopSummary.total_grams / 1000).toFixed(2)} kg
							</p>
						</div>
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Varieties</p>
							<p class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
								{hopSummary.unique_varieties}
							</p>
						</div>
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Lots</p>
							<p class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
								{hopSummary.total_items}
							</p>
						</div>
					</div>
				{/if}

				<div class="flex items-center justify-between gap-4">
					<input
						type="text"
						placeholder="Search hops..."
						bind:value={hopSearchQuery}
						class="flex-1 rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800"
					/>
					<button
						onclick={() => openHopModal()}
						class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
					>
						Add Hops
					</button>
				</div>

				{#if filteredHops().length === 0}
					<div class="rounded-lg border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-700">
						<p class="text-zinc-500 dark:text-zinc-400">
							{hopSearchQuery ? 'No hops match your search' : 'No hops in inventory'}
						</p>
					</div>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="border-b border-zinc-200 dark:border-zinc-700">
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Variety</th>
									<th class="py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">Amount</th>
									<th class="py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">AA%</th>
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Form</th>
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Year</th>
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Location</th>
									<th class="py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#each filteredHops() as hop}
									<tr class="border-b border-zinc-100 dark:border-zinc-800">
										<td class="py-3 font-medium text-zinc-900 dark:text-zinc-100">{hop.variety}</td>
										<td class="py-3 text-right text-zinc-600 dark:text-zinc-300">
											{hop.amount_grams >= 1000
												? `${(hop.amount_grams / 1000).toFixed(2)} kg`
												: `${hop.amount_grams.toFixed(0)} g`}
										</td>
										<td class="py-3 text-right text-zinc-600 dark:text-zinc-300">
											{hop.alpha_acid_percent?.toFixed(1) || '--'}
										</td>
										<td class="py-3 capitalize text-zinc-600 dark:text-zinc-300">{hop.form}</td>
										<td class="py-3 text-zinc-600 dark:text-zinc-300">{hop.crop_year || '--'}</td>
										<td class="py-3 text-zinc-500 dark:text-zinc-400">{hop.storage_location || '--'}</td>
										<td class="py-3 text-right">
											<button
												onclick={() => openAdjustModal(hop)}
												class="text-amber-600 hover:underline dark:text-amber-400"
											>
												Adjust
											</button>
											<span class="mx-1 text-zinc-300">|</span>
											<button
												onclick={() => openHopModal(hop)}
												class="text-zinc-600 hover:underline dark:text-zinc-400"
											>
												Edit
											</button>
											<span class="mx-1 text-zinc-300">|</span>
											<button
												onclick={() => (deleteTarget = { type: 'hop', item: hop })}
												class="text-red-600 hover:underline dark:text-red-400"
											>
												Delete
											</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		{/if}

		<!-- Yeast Tab -->
		{#if activeTab === 'yeast'}
			<div class="space-y-4">
				<!-- Summary cards -->
				{#if yeastSummary}
					<div class="grid gap-4 sm:grid-cols-4">
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Total Packs</p>
							<p class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
								{yeastSummary.total_quantity}
							</p>
						</div>
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Strains</p>
							<p class="text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
								{yeastSummary.total_items}
							</p>
						</div>
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Expiring Soon</p>
							<p class="text-2xl font-semibold {yeastSummary.expiring_soon > 0 ? 'text-amber-600' : 'text-zinc-900 dark:text-zinc-100'}">
								{yeastSummary.expiring_soon}
							</p>
						</div>
						<div class="rounded-lg border border-zinc-200 bg-white p-4 dark:border-zinc-700 dark:bg-zinc-800">
							<p class="text-sm text-zinc-500 dark:text-zinc-400">Expired</p>
							<p class="text-2xl font-semibold {yeastSummary.expired > 0 ? 'text-red-600' : 'text-zinc-900 dark:text-zinc-100'}">
								{yeastSummary.expired}
							</p>
						</div>
					</div>
				{/if}

				<!-- Expiring soon warning -->
				{#if expiringYeasts.length > 0}
					<div class="rounded-lg border border-amber-200 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-900/20">
						<p class="font-medium text-amber-800 dark:text-amber-200">Yeast expiring within 30 days:</p>
						<ul class="mt-2 space-y-1 text-sm text-amber-700 dark:text-amber-300">
							{#each expiringYeasts.slice(0, 5) as yeast}
								<li>
									{yeast.yeast_strain?.name || yeast.custom_name} - expires {formatDate(yeast.expiry_date)}
								</li>
							{/each}
							{#if expiringYeasts.length > 5}
								<li class="text-amber-600">...and {expiringYeasts.length - 5} more</li>
							{/if}
						</ul>
					</div>
				{/if}

				<div class="flex flex-wrap items-center justify-between gap-4">
					<div class="flex items-center gap-4">
						<input
							type="text"
							placeholder="Search yeast..."
							bind:value={yeastSearchQuery}
							class="rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-600 dark:bg-zinc-800"
						/>
						<label class="flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-400">
							<input type="checkbox" bind:checked={includeExpired} onchange={loadData} />
							Show expired
						</label>
					</div>
					<button
						onclick={() => openYeastModal()}
						class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600"
					>
						Add Yeast
					</button>
				</div>

				{#if filteredYeasts().length === 0}
					<div class="rounded-lg border border-dashed border-zinc-300 p-8 text-center dark:border-zinc-700">
						<p class="text-zinc-500 dark:text-zinc-400">
							{yeastSearchQuery ? 'No yeast matches your search' : 'No yeast in inventory'}
						</p>
					</div>
				{:else}
					<div class="overflow-x-auto">
						<table class="w-full text-sm">
							<thead>
								<tr class="border-b border-zinc-200 dark:border-zinc-700">
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Strain</th>
									<th class="py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">Qty</th>
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Form</th>
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Expiry</th>
									<th class="py-3 text-left font-medium text-zinc-500 dark:text-zinc-400">Location</th>
									<th class="py-3 text-right font-medium text-zinc-500 dark:text-zinc-400">Actions</th>
								</tr>
							</thead>
							<tbody>
								{#each filteredYeasts() as yeast}
									<tr class="border-b border-zinc-100 dark:border-zinc-800">
										<td class="py-3">
											<div class="font-medium text-zinc-900 dark:text-zinc-100">
												{yeast.yeast_strain?.name || yeast.custom_name}
											</div>
											{#if yeast.yeast_strain?.product_id}
												<div class="text-xs text-zinc-500 dark:text-zinc-400">
													{yeast.yeast_strain.producer} - {yeast.yeast_strain.product_id}
												</div>
											{/if}
											{#if yeast.generation}
												<div class="text-xs text-amber-600 dark:text-amber-400">
													Gen {yeast.generation} (harvested)
												</div>
											{/if}
										</td>
										<td class="py-3 text-right text-zinc-600 dark:text-zinc-300">{yeast.quantity}</td>
										<td class="py-3 capitalize text-zinc-600 dark:text-zinc-300">{yeast.form}</td>
										<td class="py-3 {getExpiryClass(yeast.expiry_date)}">
											{formatDate(yeast.expiry_date)}
											{#if getDaysUntilExpiry(yeast.expiry_date) !== null}
												<span class="text-xs">
													({getDaysUntilExpiry(yeast.expiry_date)}d)
												</span>
											{/if}
										</td>
										<td class="py-3 text-zinc-500 dark:text-zinc-400">{yeast.storage_location || '--'}</td>
										<td class="py-3 text-right">
											{#if yeast.quantity > 0}
												<button
													onclick={() => handleUseYeast(yeast)}
													class="text-green-600 hover:underline dark:text-green-400"
												>
													Use 1
												</button>
												<span class="mx-1 text-zinc-300">|</span>
											{/if}
											<button
												onclick={() => openYeastModal(yeast)}
												class="text-zinc-600 hover:underline dark:text-zinc-400"
											>
												Edit
											</button>
											<span class="mx-1 text-zinc-300">|</span>
											<button
												onclick={() => (deleteTarget = { type: 'yeast', item: yeast })}
												class="text-red-600 hover:underline dark:text-red-400"
											>
												Delete
											</button>
										</td>
									</tr>
								{/each}
							</tbody>
						</table>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
</div>

<!-- Equipment Modal -->
{#if showEquipmentModal}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
		<div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-800">
			<h2 class="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				{editingEquipment ? 'Edit Equipment' : 'Add Equipment'}
			</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Name *</label>
					<input
						type="text"
						bind:value={newEquipment.name}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						placeholder="My Fermenter"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Type *</label>
					<select
						bind:value={newEquipment.type}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					>
						{#each equipmentTypes as type}
							<option value={type.value}>{type.label}</option>
						{/each}
					</select>
				</div>
				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Brand</label>
						<input
							type="text"
							bind:value={newEquipment.brand}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						/>
					</div>
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Model</label>
						<input
							type="text"
							bind:value={newEquipment.model}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						/>
					</div>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Capacity (L)</label>
					<input
						type="number"
						step="0.1"
						bind:value={newEquipment.capacity_liters}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Notes</label>
					<textarea
						bind:value={newEquipment.notes}
						rows="2"
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					></textarea>
				</div>
				<label class="flex items-center gap-2">
					<input type="checkbox" bind:checked={newEquipment.is_active} />
					<span class="text-sm text-zinc-700 dark:text-zinc-300">Active</span>
				</label>
			</div>
			<div class="mt-6 flex justify-end gap-3">
				<button
					onclick={() => (showEquipmentModal = false)}
					class="rounded-lg border border-zinc-300 px-4 py-2 text-sm dark:border-zinc-600"
				>
					Cancel
				</button>
				<button
					onclick={handleSaveEquipment}
					disabled={saving || !newEquipment.name.trim()}
					class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Hop Modal -->
{#if showHopModal}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
		<div class="w-full max-w-md rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-800">
			<h2 class="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				{editingHop ? 'Edit Hop' : 'Add Hop'}
			</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Variety *</label>
					<input
						type="text"
						bind:value={newHop.variety}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						placeholder="Citra"
					/>
				</div>
				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Amount (g) *</label>
						<input
							type="number"
							step="1"
							bind:value={newHop.amount_grams}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						/>
					</div>
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Alpha Acid %</label>
						<input
							type="number"
							step="0.1"
							bind:value={newHop.alpha_acid_percent}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						/>
					</div>
				</div>
				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Form</label>
						<select
							bind:value={newHop.form}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						>
							<option value="pellet">Pellet</option>
							<option value="leaf">Leaf</option>
							<option value="plug">Plug</option>
						</select>
					</div>
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Crop Year</label>
						<input
							type="number"
							bind:value={newHop.crop_year}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						/>
					</div>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Storage Location</label>
					<input
						type="text"
						bind:value={newHop.storage_location}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						placeholder="Freezer A"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Notes</label>
					<textarea
						bind:value={newHop.notes}
						rows="2"
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					></textarea>
				</div>
			</div>
			<div class="mt-6 flex justify-end gap-3">
				<button
					onclick={() => (showHopModal = false)}
					class="rounded-lg border border-zinc-300 px-4 py-2 text-sm dark:border-zinc-600"
				>
					Cancel
				</button>
				<button
					onclick={handleSaveHop}
					disabled={saving || !newHop.variety.trim()}
					class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Adjust Hop Amount Modal -->
{#if showAdjustModal && adjustingHop}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
		<div class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-800">
			<h2 class="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				Adjust {adjustingHop.variety}
			</h2>
			<p class="mb-4 text-sm text-zinc-500 dark:text-zinc-400">
				Current: {adjustingHop.amount_grams}g
			</p>
			<div>
				<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
					Amount to add/subtract (g)
				</label>
				<input
					type="number"
					bind:value={adjustAmount}
					class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					placeholder="-50 or 100"
				/>
				<p class="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
					Use negative numbers to subtract
				</p>
			</div>
			<div class="mt-6 flex justify-end gap-3">
				<button
					onclick={() => (showAdjustModal = false)}
					class="rounded-lg border border-zinc-300 px-4 py-2 text-sm dark:border-zinc-600"
				>
					Cancel
				</button>
				<button
					onclick={handleAdjustHop}
					disabled={saving || adjustAmount === 0}
					class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
				>
					{saving ? 'Adjusting...' : 'Adjust'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Yeast Modal -->
{#if showYeastModal}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
		<div class="w-full max-w-md max-h-[90vh] overflow-y-auto rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-800">
			<h2 class="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
				{editingYeast ? 'Edit Yeast' : 'Add Yeast'}
			</h2>
			<div class="space-y-4">
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Yeast Strain</label>
					<select
						bind:value={newYeast.yeast_strain_id}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					>
						<option value={undefined}>-- Select or enter custom --</option>
						{#each yeastStrains as strain}
							<option value={strain.id}>
								{strain.name} ({strain.producer} - {strain.product_id})
							</option>
						{/each}
					</select>
				</div>
				{#if !newYeast.yeast_strain_id}
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Custom Name</label>
						<input
							type="text"
							bind:value={newYeast.custom_name}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
							placeholder="My harvested strain"
						/>
					</div>
				{/if}
				<div class="grid grid-cols-2 gap-4">
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Quantity</label>
						<input
							type="number"
							min="0"
							bind:value={newYeast.quantity}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						/>
					</div>
					<div>
						<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Form</label>
						<select
							bind:value={newYeast.form}
							class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						>
							<option value="dry">Dry</option>
							<option value="liquid">Liquid</option>
							<option value="slant">Slant</option>
							<option value="harvested">Harvested</option>
						</select>
					</div>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Expiry Date</label>
					<input
						type="date"
						bind:value={newYeast.expiry_date}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Storage Location</label>
					<input
						type="text"
						bind:value={newYeast.storage_location}
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
						placeholder="Fridge A"
					/>
				</div>
				<div>
					<label class="block text-sm font-medium text-zinc-700 dark:text-zinc-300">Notes</label>
					<textarea
						bind:value={newYeast.notes}
						rows="2"
						class="mt-1 w-full rounded-lg border border-zinc-300 px-3 py-2 dark:border-zinc-600 dark:bg-zinc-700"
					></textarea>
				</div>
			</div>
			<div class="mt-6 flex justify-end gap-3">
				<button
					onclick={() => (showYeastModal = false)}
					class="rounded-lg border border-zinc-300 px-4 py-2 text-sm dark:border-zinc-600"
				>
					Cancel
				</button>
				<button
					onclick={handleSaveYeast}
					disabled={saving}
					class="rounded-lg bg-amber-500 px-4 py-2 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
				>
					{saving ? 'Saving...' : 'Save'}
				</button>
			</div>
		</div>
	</div>
{/if}

<!-- Delete Confirmation Modal -->
{#if deleteTarget}
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
		<div class="w-full max-w-sm rounded-lg bg-white p-6 shadow-xl dark:bg-zinc-800">
			<h2 class="mb-4 text-lg font-semibold text-zinc-900 dark:text-zinc-100">Confirm Delete</h2>
			<p class="text-zinc-600 dark:text-zinc-300">
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
			<div class="mt-6 flex justify-end gap-3">
				<button
					onclick={() => (deleteTarget = null)}
					class="rounded-lg border border-zinc-300 px-4 py-2 text-sm dark:border-zinc-600"
				>
					Cancel
				</button>
				<button
					onclick={handleDelete}
					disabled={deleting}
					class="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700 disabled:opacity-50"
				>
					{deleting ? 'Deleting...' : 'Delete'}
				</button>
			</div>
		</div>
	</div>
{/if}
