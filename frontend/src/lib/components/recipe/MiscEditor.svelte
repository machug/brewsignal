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

	function getTypeIcon(type: string): string {
		const icons: Record<string, string> = {
			spice: 'S',
			fining: 'F',
			water_agent: 'W',
			herb: 'H',
			flavor: 'L',
			other: 'O'
		};
		return icons[type] || 'M';
	}

	function getTypeColor(type: string): string {
		const colors: Record<string, string> = {
			spice: 'var(--warning)',
			fining: 'var(--info)',
			water_agent: 'rgb(56, 189, 248)',
			herb: 'var(--positive)',
			flavor: 'rgb(168, 85, 247)',
			other: 'var(--text-muted)'
		};
		return colors[type] || 'var(--text-muted)';
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
					<div class="type-badge" style="background: {getTypeColor(item.type)}">
						{getTypeIcon(item.type)}
					</div>
					<input
						type="text"
						class="input-name"
						value={item.name}
						placeholder="Ingredient name"
						onchange={(e) => updateItem(i, 'name', e.currentTarget.value)}
					/>
					<select
						class="input-type"
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
						class="input-use"
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
							class="input-amount"
							value={item.amount_kg ?? ''}
							placeholder="0"
							onchange={(e) => updateItem(i, 'amount_kg', parseFloat(e.currentTarget.value) || 0)}
						/>
						<select
							class="input-unit"
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
							class="input-time"
							value={item.time_min ?? ''}
							placeholder="0"
							onchange={(e) => updateItem(i, 'time_min', parseFloat(e.currentTarget.value) || 0)}
						/>
						<span class="unit">min</span>
					</div>
					<button type="button" class="btn-remove" onclick={() => removeItem(i)}>×</button>
				</div>
			{/each}
		</div>
	{/if}
</div>

<style>
	.editor-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-4);
	}

	.section-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.section-header h4 {
		margin: 0;
		font-size: 14px;
		font-weight: 600;
		color: var(--text-primary);
	}

	.btn-add {
		padding: var(--space-2) var(--space-3);
		background: var(--recipe-accent);
		color: var(--gray-950);
		border: none;
		border-radius: 6px;
		font-size: 13px;
		font-weight: 500;
		cursor: pointer;
		transition: background var(--transition), transform var(--transition);
	}

	.btn-add:hover {
		filter: brightness(1.1);
		transform: translateY(-1px);
	}

	.empty-state {
		color: var(--text-muted);
		font-size: 14px;
		text-align: center;
		padding: var(--space-6);
		background: var(--bg-surface);
		border: 1px dashed var(--border-subtle);
		border-radius: 6px;
		margin: 0;
	}

	.items-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.item-row {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		padding: var(--space-3);
		background: var(--bg-elevated);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		flex-wrap: wrap;
	}

	.type-badge {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 24px;
		height: 24px;
		border-radius: 4px;
		font-size: 11px;
		font-weight: 700;
		color: var(--gray-950);
		flex-shrink: 0;
	}

	.input-name {
		flex: 1;
		min-width: 120px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
	}

	.input-name:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.input-type,
	.input-use {
		width: 100px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 13px;
		cursor: pointer;
	}

	.input-type:focus,
	.input-use:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.amount-group {
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.input-amount {
		width: 60px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-size: 13px;
		text-align: right;
	}

	.input-amount:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.input-unit {
		width: 60px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-size: 12px;
		cursor: pointer;
	}

	.input-unit:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.time-group {
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.input-time {
		width: 60px;
		padding: var(--space-2);
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 4px;
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-size: 13px;
		text-align: right;
	}

	.input-time:focus {
		outline: none;
		border-color: var(--recipe-accent);
	}

	.unit {
		font-size: 12px;
		color: var(--text-muted);
		min-width: 24px;
	}

	.btn-remove {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		padding: 0;
		background: transparent;
		border: 1px solid var(--border-subtle);
		border-radius: 4px;
		color: var(--text-muted);
		font-size: 18px;
		cursor: pointer;
		transition: all var(--transition);
		flex-shrink: 0;
	}

	.btn-remove:hover {
		background: var(--negative-muted);
		border-color: var(--negative);
		color: var(--negative);
	}

	@media (max-width: 768px) {
		.item-row {
			gap: var(--space-2);
		}

		.input-name {
			flex-basis: calc(100% - 40px);
			order: 1;
		}

		.type-badge {
			order: 0;
		}

		.btn-remove {
			order: 2;
		}

		.input-type,
		.input-use {
			flex: 1;
			min-width: 80px;
			order: 3;
		}

		.amount-group,
		.time-group {
			order: 4;
		}
	}
</style>
