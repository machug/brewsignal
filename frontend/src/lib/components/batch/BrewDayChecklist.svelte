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
				const savedMap = new Map<string, ChecklistItem>(parsed.map((item: ChecklistItem) => [item.id, item]));

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
	<button type="button" class="checklist-header" onclick={() => expanded = !expanded} aria-expanded={expanded}>
		<div class="header-left">
			<span class="title">Checklist</span>
			<span class="progress-text">{checkedCount}/{totalCount}</span>
		</div>
		<div class="header-right">
			<div class="mini-progress" class:done={progress === 100}>
				<div class="mini-fill" style="width: {progress}%"></div>
			</div>
			<svg class="chevron" class:expanded fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
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
		border-top: 1px solid var(--rule-strong);
		min-width: 0;
	}
	.checklist-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		min-height: 44px;
		padding: var(--space-xs) 0;
		cursor: pointer;
		text-align: left;
	}
	.header-left {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
	}
	.title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-muted);
	}
	.progress-text {
		font-size: var(--text-xs);
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		color: var(--ink-secondary);
	}
	.header-right {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
	}
	.mini-progress {
		width: 3rem;
		height: 3px;
		background: var(--rule-hairline);
	}
	.mini-fill {
		height: 100%;
		background: var(--ink-secondary);
		transition: width 300ms var(--ease-out-quart);
	}
	.mini-progress.done .mini-fill {
		background: var(--status-steady);
	}
	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		transition: transform 150ms var(--ease-out-quart);
	}
	.chevron.expanded {
		transform: rotate(180deg);
	}
	.next-items,
	.all-items {
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--rule-hairline);
	}
	.all-items {
		max-height: 320px;
		overflow-y: auto;
	}
	.next-item,
	.item-row {
		display: flex;
		align-items: center;
		gap: var(--space-sm);
		min-height: 44px;
		padding: var(--space-2xs) var(--space-2xs);
		border-bottom: 1px solid var(--rule-hairline);
		cursor: pointer;
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}
	.next-item:hover,
	.item-row:hover {
		background: var(--bg-surface);
	}
	.item-row.checked {
		color: var(--ink-muted);
	}
	.item-row.checked .item-text {
		text-decoration: line-through;
	}
	input[type="checkbox"] {
		width: 1.125rem;
		height: 1.125rem;
		accent-color: var(--accent);
		cursor: pointer;
	}
	@media (prefers-reduced-motion: reduce) {
		.mini-fill,
		.chevron {
			transition: none;
		}
	}
</style>
