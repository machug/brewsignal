<script lang="ts">
	import type { RecipeResponse } from '$lib/api';

	interface Props {
		recipe: RecipeResponse;
		batchId: number;
	}

	interface ChecklistItem {
		id: string;
		text: string;
		checked: boolean;
		category: 'prep' | 'mash' | 'boil' | 'post-boil' | 'custom';
	}

	let { recipe, batchId }: Props = $props();

	// Checklist items
	let items = $state<ChecklistItem[]>([]);
	let newItemText = $state('');
	let showAddItem = $state(false);

	// Storage key for this batch
	let storageKey = $derived(`brewday-checklist-${batchId}`);

	// Generate checklist from recipe
	function generateFromRecipe(): ChecklistItem[] {
		const generated: ChecklistItem[] = [];

		// Prep items
		generated.push({
			id: 'prep-sanitize',
			text: 'Sanitize all equipment',
			checked: false,
			category: 'prep'
		});
		generated.push({
			id: 'prep-water',
			text: `Heat strike water (${recipe.batch_size_liters ? Math.round(recipe.batch_size_liters * 1.3) : '--'}L)`,
			checked: false,
			category: 'prep'
		});

		// Fermentables (prep)
		if (recipe.fermentables) {
			recipe.fermentables.forEach((f, i) => {
				const amount = f.amount_kg ? `${(f.amount_kg * 1000).toFixed(0)}g` : '';
				generated.push({
					id: `ferm-${i}`,
					text: `Mill grain: ${f.name} ${amount}`,
					checked: false,
					category: 'prep'
				});
			});
		}

		// Mash items
		generated.push({
			id: 'mash-dough-in',
			text: 'Dough in - add grain to strike water',
			checked: false,
			category: 'mash'
		});
		generated.push({
			id: 'mash-temp',
			text: 'Check mash temperature',
			checked: false,
			category: 'mash'
		});
		generated.push({
			id: 'mash-rest',
			text: 'Mash rest complete',
			checked: false,
			category: 'mash'
		});
		generated.push({
			id: 'mash-sparge',
			text: 'Sparge and collect wort',
			checked: false,
			category: 'mash'
		});

		// Boil items
		generated.push({
			id: 'boil-preboil',
			text: 'Record pre-boil gravity',
			checked: false,
			category: 'boil'
		});
		generated.push({
			id: 'boil-start',
			text: 'Bring to boil',
			checked: false,
			category: 'boil'
		});

		// Hop additions
		if (recipe.hops) {
			const boilHops = recipe.hops
				.filter(h => h.timing?.use === 'add_to_boil' || !h.timing?.use)
				.sort((a, b) => (b.timing?.duration?.value || 0) - (a.timing?.duration?.value || 0));

			boilHops.forEach((h, i) => {
				const time = h.timing?.duration?.value || 0;
				const amount = h.amount_grams ? `${h.amount_grams}g` : '';
				generated.push({
					id: `hop-${i}`,
					text: `Add ${h.name} ${amount} @ ${time}min`,
					checked: false,
					category: 'boil'
				});
			});
		}

		// Post-boil items
		generated.push({
			id: 'postboil-flame-off',
			text: 'Flame off / end boil',
			checked: false,
			category: 'post-boil'
		});
		generated.push({
			id: 'postboil-chill',
			text: 'Chill wort to pitch temp',
			checked: false,
			category: 'post-boil'
		});
		generated.push({
			id: 'postboil-og',
			text: 'Record original gravity (OG)',
			checked: false,
			category: 'post-boil'
		});
		generated.push({
			id: 'postboil-transfer',
			text: 'Transfer to fermenter',
			checked: false,
			category: 'post-boil'
		});
		generated.push({
			id: 'postboil-yeast',
			text: 'Pitch yeast',
			checked: false,
			category: 'post-boil'
		});
		generated.push({
			id: 'postboil-airlock',
			text: 'Seal fermenter and add airlock',
			checked: false,
			category: 'post-boil'
		});

		return generated;
	}

	// Load saved state or generate new
	function loadChecklist() {
		try {
			const saved = localStorage.getItem(storageKey);
			if (saved) {
				const parsed = JSON.parse(saved);
				// Merge saved checked states with generated items
				const generated = generateFromRecipe();
				const savedMap = new Map(parsed.map((item: ChecklistItem) => [item.id, item]));

				// Update generated items with saved checked state
				for (const item of generated) {
					const savedItem = savedMap.get(item.id);
					if (savedItem) {
						item.checked = savedItem.checked;
					}
				}

				// Add any custom items that were saved
				const customItems = parsed.filter((item: ChecklistItem) => item.category === 'custom');
				items = [...generated, ...customItems];
			} else {
				items = generateFromRecipe();
			}
		} catch {
			items = generateFromRecipe();
		}
	}

	// Save checklist state
	function saveChecklist() {
		try {
			localStorage.setItem(storageKey, JSON.stringify(items));
		} catch (e) {
			console.warn('Failed to save checklist:', e);
		}
	}

	// Toggle item checked state
	function toggleItem(id: string) {
		items = items.map(item =>
			item.id === id ? { ...item, checked: !item.checked } : item
		);
		saveChecklist();
	}

	// Add custom item
	function addCustomItem() {
		if (!newItemText.trim()) return;

		const newItem: ChecklistItem = {
			id: `custom-${Date.now()}`,
			text: newItemText.trim(),
			checked: false,
			category: 'custom'
		};

		items = [...items, newItem];
		newItemText = '';
		showAddItem = false;
		saveChecklist();
	}

	// Remove custom item
	function removeItem(id: string) {
		items = items.filter(item => item.id !== id);
		saveChecklist();
	}

	// Reset all items
	function resetChecklist() {
		if (confirm('Reset all checklist items to unchecked?')) {
			items = items.map(item => ({ ...item, checked: false }));
			saveChecklist();
		}
	}

	// Calculate progress
	let progress = $derived.by(() => {
		if (items.length === 0) return 0;
		const checked = items.filter(i => i.checked).length;
		return Math.round((checked / items.length) * 100);
	});

	// Group items by category
	let groupedItems = $derived.by(() => {
		const groups: Record<string, ChecklistItem[]> = {
			prep: [],
			mash: [],
			boil: [],
			'post-boil': [],
			custom: []
		};

		for (const item of items) {
			groups[item.category].push(item);
		}

		return groups;
	});

	// Category display names
	const categoryNames: Record<string, string> = {
		prep: 'Preparation',
		mash: 'Mash',
		boil: 'Boil',
		'post-boil': 'Post-Boil',
		custom: 'Custom'
	};

	// Load on mount
	$effect(() => {
		loadChecklist();
	});
</script>

<div class="checklist-card">
	<div class="checklist-header">
		<div class="header-left">
			<h3 class="checklist-title">Brew Day Checklist</h3>
			<span class="progress-badge">{progress}%</span>
		</div>
		<button type="button" class="reset-btn" onclick={resetChecklist} title="Reset all items">
			<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
			</svg>
		</button>
	</div>

	<div class="progress-bar">
		<div class="progress-fill" style="width: {progress}%"></div>
	</div>

	<div class="checklist-groups">
		{#each Object.entries(groupedItems) as [category, categoryItems]}
			{#if categoryItems.length > 0}
				<div class="category-group">
					<h4 class="category-title">{categoryNames[category]}</h4>
					<div class="items-list">
						{#each categoryItems as item (item.id)}
							<label class="checklist-item" class:checked={item.checked}>
								<input
									type="checkbox"
									checked={item.checked}
									onchange={() => toggleItem(item.id)}
								/>
								<span class="item-text">{item.text}</span>
								{#if item.category === 'custom'}
									<button
										type="button"
										class="remove-btn"
										onclick={() => removeItem(item.id)}
										title="Remove item"
									>
										×
									</button>
								{/if}
							</label>
						{/each}
					</div>
				</div>
			{/if}
		{/each}
	</div>

	<!-- Add custom item -->
	<div class="add-section">
		{#if showAddItem}
			<div class="add-form">
				<input
					type="text"
					class="add-input"
					placeholder="Add custom item..."
					bind:value={newItemText}
					onkeydown={(e) => e.key === 'Enter' && addCustomItem()}
				/>
				<button type="button" class="add-btn" onclick={addCustomItem}>Add</button>
				<button type="button" class="cancel-btn" onclick={() => { showAddItem = false; newItemText = ''; }}>Cancel</button>
			</div>
		{:else}
			<button type="button" class="show-add-btn" onclick={() => showAddItem = true}>
				<svg class="btn-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 4v16m8-8H4" />
				</svg>
				Add custom item
			</button>
		{/if}
	</div>
</div>

<style>
	.checklist-card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		padding: 1.25rem;
	}

	.checklist-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.75rem;
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.checklist-title {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
	}

	.progress-badge {
		font-size: 0.6875rem;
		font-weight: 600;
		padding: 0.125rem 0.5rem;
		background: var(--positive-muted);
		color: var(--positive);
		border-radius: 9999px;
	}

	.reset-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 0.375rem;
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		border-radius: 0.25rem;
	}

	.reset-btn:hover {
		color: var(--text-secondary);
		background: var(--bg-elevated);
	}

	.btn-icon {
		width: 1rem;
		height: 1rem;
	}

	.progress-bar {
		height: 4px;
		background: var(--bg-elevated);
		border-radius: 2px;
		overflow: hidden;
		margin-bottom: 1rem;
	}

	.progress-fill {
		height: 100%;
		background: var(--positive);
		border-radius: 2px;
		transition: width 0.3s ease;
	}

	.checklist-groups {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.category-group {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.category-title {
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0;
		padding-bottom: 0.25rem;
		border-bottom: 1px solid var(--border-subtle);
	}

	.items-list {
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
	}

	.checklist-item {
		display: flex;
		align-items: center;
		gap: 0.625rem;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.checklist-item:hover {
		background: var(--bg-hover);
	}

	.checklist-item.checked {
		opacity: 0.6;
	}

	.checklist-item.checked .item-text {
		text-decoration: line-through;
		color: var(--text-muted);
	}

	.checklist-item input[type="checkbox"] {
		width: 1rem;
		height: 1rem;
		accent-color: var(--positive);
		cursor: pointer;
	}

	.item-text {
		flex: 1;
		font-size: 0.8125rem;
		color: var(--text-primary);
	}

	.remove-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.25rem;
		height: 1.25rem;
		font-size: 1rem;
		font-weight: 500;
		background: transparent;
		border: none;
		color: var(--text-muted);
		cursor: pointer;
		border-radius: 0.25rem;
		opacity: 0;
		transition: opacity 0.15s ease;
	}

	.checklist-item:hover .remove-btn {
		opacity: 1;
	}

	.remove-btn:hover {
		color: var(--negative);
		background: rgba(239, 68, 68, 0.1);
	}

	/* Add section */
	.add-section {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--border-subtle);
	}

	.show-add-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 0.5rem;
		width: 100%;
		padding: 0.625rem;
		font-size: 0.8125rem;
		font-weight: 500;
		background: transparent;
		border: 1px dashed var(--border-default);
		border-radius: 0.375rem;
		color: var(--text-secondary);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.show-add-btn:hover {
		background: var(--bg-elevated);
		border-color: var(--border-subtle);
		color: var(--text-primary);
	}

	.add-form {
		display: flex;
		gap: 0.5rem;
	}

	.add-input {
		flex: 1;
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.375rem;
		color: var(--text-primary);
	}

	.add-input:focus {
		outline: none;
		border-color: var(--accent);
	}

	.add-btn {
		padding: 0.5rem 1rem;
		font-size: 0.8125rem;
		font-weight: 500;
		background: var(--accent);
		border: none;
		border-radius: 0.375rem;
		color: white;
		cursor: pointer;
	}

	.add-btn:hover {
		background: var(--accent-hover);
	}

	.cancel-btn {
		padding: 0.5rem 0.75rem;
		font-size: 0.8125rem;
		font-weight: 500;
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 0.375rem;
		color: var(--text-secondary);
		cursor: pointer;
	}

	.cancel-btn:hover {
		background: var(--bg-hover);
	}
</style>
