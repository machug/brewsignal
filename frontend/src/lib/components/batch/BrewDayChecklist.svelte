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

	// State
	let items = $state<ChecklistItem[]>([]);
	let expanded = $state(false);

	// Storage key for this batch
	let storageKey = $derived(`brewday-checklist-${batchId}`);

	// Generate checklist from recipe
	function generateFromRecipe(): ChecklistItem[] {
		const generated: ChecklistItem[] = [];

		// Prep items
		generated.push({ id: 'prep-sanitize', text: 'Sanitize equipment', checked: false, category: 'prep' });
		generated.push({ id: 'prep-water', text: `Heat strike water`, checked: false, category: 'prep' });

		// Fermentables (prep)
		if (recipe.fermentables) {
			recipe.fermentables.forEach((f, i) => {
				generated.push({ id: `ferm-${i}`, text: `Mill: ${f.name}`, checked: false, category: 'prep' });
			});
		}

		// Mash items
		generated.push({ id: 'mash-dough-in', text: 'Dough in', checked: false, category: 'mash' });
		generated.push({ id: 'mash-temp', text: 'Check mash temp', checked: false, category: 'mash' });
		generated.push({ id: 'mash-sparge', text: 'Sparge', checked: false, category: 'mash' });

		// Boil items
		generated.push({ id: 'boil-preboil', text: 'Record pre-boil gravity', checked: false, category: 'boil' });
		generated.push({ id: 'boil-start', text: 'Bring to boil', checked: false, category: 'boil' });

		// Hop additions
		if (recipe.hops) {
			const boilHops = recipe.hops
				.filter(h => h.timing?.use === 'add_to_boil' || !h.timing?.use)
				.sort((a, b) => (b.timing?.duration?.value || 0) - (a.timing?.duration?.value || 0));

			boilHops.forEach((h, i) => {
				const time = h.timing?.duration?.value || 0;
				generated.push({ id: `hop-${i}`, text: `${h.name} @ ${time}min`, checked: false, category: 'boil' });
			});
		}

		// Post-boil items
		generated.push({ id: 'postboil-chill', text: 'Chill wort', checked: false, category: 'post-boil' });
		generated.push({ id: 'postboil-og', text: 'Record OG', checked: false, category: 'post-boil' });
		generated.push({ id: 'postboil-transfer', text: 'Transfer to fermenter', checked: false, category: 'post-boil' });
		generated.push({ id: 'postboil-yeast', text: 'Pitch yeast', checked: false, category: 'post-boil' });

		return generated;
	}

	// Load saved state or generate new
	function loadChecklist() {
		try {
			const saved = localStorage.getItem(storageKey);
			if (saved) {
				const parsed = JSON.parse(saved);
				const generated = generateFromRecipe();
				const savedMap = new Map(parsed.map((item: ChecklistItem) => [item.id, item]));

				for (const item of generated) {
					const savedItem = savedMap.get(item.id);
					if (savedItem) {
						item.checked = savedItem.checked;
					}
				}

				const customItems = parsed.filter((item: ChecklistItem) => item.category === 'custom');
				items = [...generated, ...customItems];
			} else {
				items = generateFromRecipe();
			}
		} catch {
			items = generateFromRecipe();
		}
	}

	function saveChecklist() {
		try {
			localStorage.setItem(storageKey, JSON.stringify(items));
		} catch (e) {
			console.warn('Failed to save checklist:', e);
		}
	}

	function toggleItem(id: string) {
		items = items.map(item =>
			item.id === id ? { ...item, checked: !item.checked } : item
		);
		saveChecklist();
	}

	// Progress
	let checkedCount = $derived(items.filter(i => i.checked).length);
	let totalCount = $derived(items.length);
	let progress = $derived(totalCount > 0 ? Math.round((checkedCount / totalCount) * 100) : 0);

	// Next unchecked items (up to 3)
	let nextItems = $derived(items.filter(i => !i.checked).slice(0, 3));

	// Load on mount
	$effect(() => {
		loadChecklist();
	});
</script>

<div class="checklist-compact">
	<button type="button" class="checklist-header" onclick={() => expanded = !expanded}>
		<div class="header-left">
			<span class="check-icon" class:done={progress === 100}>
				{#if progress === 100}
					✓
				{:else}
					☐
				{/if}
			</span>
			<span class="title">Checklist</span>
			<span class="progress-text">{checkedCount}/{totalCount}</span>
		</div>
		<div class="header-right">
			<div class="mini-progress">
				<div class="mini-fill" style="width: {progress}%"></div>
			</div>
			<svg class="chevron" class:expanded fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
			</svg>
		</div>
	</button>

	{#if !expanded && nextItems.length > 0}
		<div class="next-items">
			{#each nextItems as item (item.id)}
				<label class="next-item" onclick={(e) => e.stopPropagation()}>
					<input type="checkbox" checked={item.checked} onchange={() => toggleItem(item.id)} />
					<span class="item-text">{item.text}</span>
				</label>
			{/each}
		</div>
	{/if}

	{#if expanded}
		<div class="all-items">
			{#each items as item (item.id)}
				<label class="item-row" class:checked={item.checked}>
					<input type="checkbox" checked={item.checked} onchange={() => toggleItem(item.id)} />
					<span class="item-text">{item.text}</span>
				</label>
			{/each}
		</div>
	{/if}
</div>

<style>
	.checklist-compact {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.75rem;
		overflow: hidden;
	}

	.checklist-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		padding: 0.875rem 1rem;
		background: transparent;
		border: none;
		cursor: pointer;
		text-align: left;
	}

	.checklist-header:hover {
		background: var(--bg-hover);
	}

	.header-left {
		display: flex;
		align-items: center;
		gap: 0.625rem;
	}

	.check-icon {
		font-size: 0.875rem;
		color: var(--text-muted);
	}

	.check-icon.done {
		color: var(--positive);
	}

	.title {
		font-size: 0.875rem;
		font-weight: 500;
		color: var(--text-primary);
	}

	.progress-text {
		font-size: 0.75rem;
		font-family: var(--font-mono);
		color: var(--text-muted);
	}

	.header-right {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.mini-progress {
		width: 3rem;
		height: 4px;
		background: var(--bg-elevated);
		border-radius: 2px;
		overflow: hidden;
	}

	.mini-fill {
		height: 100%;
		background: var(--positive);
		border-radius: 2px;
		transition: width 0.3s ease;
	}

	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--text-muted);
		transition: transform 0.2s ease;
	}

	.chevron.expanded {
		transform: rotate(180deg);
	}

	.next-items {
		padding: 0 1rem 0.875rem;
		display: flex;
		flex-direction: column;
		gap: 0.375rem;
	}

	.next-item {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0.625rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		cursor: pointer;
		font-size: 0.8125rem;
	}

	.next-item:hover {
		background: var(--bg-hover);
	}

	.next-item input[type="checkbox"] {
		width: 0.875rem;
		height: 0.875rem;
		accent-color: var(--positive);
		cursor: pointer;
	}

	.next-item .item-text {
		color: var(--text-primary);
	}

	.all-items {
		padding: 0 1rem 1rem;
		display: flex;
		flex-direction: column;
		gap: 0.25rem;
		max-height: 300px;
		overflow-y: auto;
	}

	.item-row {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		padding: 0.375rem 0.625rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		cursor: pointer;
		font-size: 0.8125rem;
	}

	.item-row:hover {
		background: var(--bg-hover);
	}

	.item-row.checked {
		opacity: 0.5;
	}

	.item-row.checked .item-text {
		text-decoration: line-through;
		color: var(--text-muted);
	}

	.item-row input[type="checkbox"] {
		width: 0.875rem;
		height: 0.875rem;
		accent-color: var(--positive);
		cursor: pointer;
	}

	.item-row .item-text {
		color: var(--text-primary);
	}
</style>
