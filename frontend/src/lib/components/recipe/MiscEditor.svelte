<script lang="ts">
	export interface MiscInput {
		name: string;
		type: string;
		use: string;
		time_min?: number;
		amount_kg?: number;
		amount_unit?: string;
		use_for?: string;
		notes?: string;
	}

	interface Props {
		items: MiscInput[];
		onUpdate: (items: MiscInput[]) => void;
	}

	let { items = [], onUpdate }: Props = $props();

	let localItems = $state<MiscInput[]>([]);

	$effect(() => {
		localItems = [...items];
	});

	function addItem() {
		const newItem: MiscInput = {
			name: '',
			type: 'spice',
			use: 'boil',
			time_min: 0,
			amount_kg: 0,
			amount_unit: 'g'
		};
		localItems = [...localItems, newItem];
		onUpdate(localItems);
	}

	function removeItem(index: number) {
		localItems = localItems.filter((_, i) => i !== index);
		onUpdate(localItems);
	}

	function updateItem(index: number, field: keyof MiscInput, value: unknown) {
		localItems[index] = { ...localItems[index], [field]: value };
		onUpdate(localItems);
	}

</script>

<div class="editor-section">
	<div class="section-header">
		<h4>Miscellaneous Ingredients</h4>
		<button type="button" class="btn-add" onclick={addItem}>+ Add Item</button>
	</div>

	{#if localItems.length === 0}
		<p class="empty-state">No miscellaneous ingredients defined. Click "Add Item" to add one.</p>
	{:else}
		<div class="items-list">
			{#each localItems as item, i}
				<div class="item-row">
					<input
						type="text"
						class="input-name" aria-label="Ingredient name"
						value={item.name}
						placeholder="Ingredient name"
						onchange={(e) => updateItem(i, 'name', e.currentTarget.value)}
					/>
					<select
						class="input-type" aria-label="Ingredient type"
						value={item.type}
						onchange={(e) => updateItem(i, 'type', e.currentTarget.value)}
					>
						<option value="spice">Spice</option>
						<option value="fining">Fining</option>
						<option value="water_agent">Water Agent</option>
						<option value="herb">Herb</option>
						<option value="flavor">Flavor</option>
						<option value="other">Other</option>
					</select>
					<select
						class="input-use" aria-label="Use"
						value={item.use}
						onchange={(e) => updateItem(i, 'use', e.currentTarget.value)}
					>
						<option value="mash">Mash</option>
						<option value="sparge">Sparge</option>
						<option value="boil">Boil</option>
						<option value="primary">Primary</option>
						<option value="secondary">Secondary</option>
						<option value="bottling">Bottling</option>
					</select>
					<div class="amount-group">
						<input
							type="number"
							step="0.01"
							class="input-amount" aria-label="Amount"
							value={item.amount_kg ?? ''}
							placeholder="0"
							onchange={(e) => updateItem(i, 'amount_kg', parseFloat(e.currentTarget.value) || 0)}
						/>
						<select
							class="input-unit" aria-label="Unit"
							value={item.amount_unit || 'g'}
							onchange={(e) => updateItem(i, 'amount_unit', e.currentTarget.value)}
						>
							<option value="g">g</option>
							<option value="kg">kg</option>
							<option value="oz">oz</option>
							<option value="ml">ml</option>
							<option value="tsp">tsp</option>
							<option value="tbsp">tbsp</option>
							<option value="each">each</option>
						</select>
					</div>
					<div class="time-group">
						<input
							type="number"
							class="input-time" aria-label="Time in minutes"
							value={item.time_min ?? ''}
							placeholder="0"
							onchange={(e) => updateItem(i, 'time_min', parseFloat(e.currentTarget.value) || 0)}
						/>
						<span class="unit">min</span>
					</div>
					<button type="button" class="btn-remove" aria-label="Remove" onclick={() => removeItem(i)}>×</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.editor-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-sm);
		padding-bottom: var(--space-xs);
		border-bottom: 1px solid var(--rule-strong);
	}

	h4 {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.1em;
		color: var(--ink-secondary);
		margin: 0;
	}

	.btn-add {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		min-height: 44px;
		padding: var(--space-xs) var(--space-md);
		background: transparent;
		color: var(--ink-secondary);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		white-space: nowrap;
		cursor: pointer;
		transition: border-color var(--transition), color var(--transition);
	}

	.btn-add:hover {
		border-color: var(--ink-secondary);
		color: var(--ink-primary);
	}

	.btn-add:focus-visible,
	.btn-remove:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}

	.empty-state {
		margin: 0;
		padding: var(--space-md);
		border: 1px dashed var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-secondary);
		font-size: var(--text-sm);
	}

	/* Fields: 44px, 1px strong rule, visible accent focus ring */
	input,
	select {
		min-height: 44px;
		padding: var(--space-xs) var(--space-sm);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		color: var(--ink-primary);
		font-family: var(--font-body);
		font-size: var(--text-sm);
		box-sizing: border-box;
		min-width: 0;
	}

	input[type='number'] {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		text-align: right;
	}

	input::placeholder {
		color: var(--ink-muted);
	}

	input:focus-visible,
	select:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 1px;
		border-color: var(--accent);
	}

	.unit {
		font-size: var(--text-sm);
		color: var(--ink-muted);
		white-space: nowrap;
	}

	.btn-remove {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		width: 44px;
		height: 44px;
		padding: 0;
		background: transparent;
		color: var(--ink-muted);
		border: 1px solid transparent;
		border-radius: 4px;
		font-size: 20px;
		line-height: 1;
		cursor: pointer;
		flex-shrink: 0;
		transition: border-color var(--transition), color var(--transition);
	}

	.btn-remove:hover {
		border-color: var(--status-danger);
		color: var(--status-danger);
	}

	.items-list {
		display: flex;
		flex-direction: column;
	}

	/* Hairline rows: one row per step/item */
	.item-row {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.input-name {
		flex: 1 1 160px;
	}

	.input-type,
	.input-use {
		flex: 0 1 140px;
	}

	.input-time {
		width: 84px;
		flex: none;
	}

	.amount-group,
	.time-group {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}

	.input-amount {
		width: 88px;
	}

	.input-unit {
		width: 84px;
	}

	.item-row .input-name {
		flex: 1 1 180px;
	}

	@media (max-width: 760px) {
		.item-row .input-name {
			flex: 1 1 100%;
		}

		.item-row .btn-remove {
			margin-left: auto;
		}
	}
</style>
