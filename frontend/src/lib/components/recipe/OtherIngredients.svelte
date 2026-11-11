<script lang="ts">
	interface MiscIngredient {
		id: number;
		name: string;
		type?: string;
		use?: string;
		time_min?: number;
		amount_kg?: number;
		amount_unit?: string;
		use_for?: string;
		timing?: {
			use?: string;
		};
	}

	let { miscs }: { miscs: MiscIngredient[] } = $props();

	// Water agents live in the Water Chemistry section; everything else
	// (finings, enzymes, spices, flavors) renders here.
	// Water agents are spelled 'water agent' by importers and 'water_agent'
	// by the misc editor — normalize before filtering.
	function isWaterAgent(m: MiscIngredient): boolean {
		return (m.type ?? '').toLowerCase().replace('_', ' ') === 'water agent';
	}
	let others = $derived(miscs.filter((m) => !isWaterAgent(m)));

	function formatAmount(misc: MiscIngredient): string {
		// amount_kg holds the value in amount_unit units (legacy column name)
		if (misc.amount_kg === undefined || misc.amount_kg === null) return '--';
		const unit = misc.amount_unit || 'g';
		return `${misc.amount_kg.toFixed(misc.amount_kg < 1 ? 2 : 1)}\u2009${unit}`;
	}

	function formatUse(misc: MiscIngredient): string {
		const use = misc.use || misc.timing?.use || '';
		const useMap: Record<string, string> = {
			add_to_mash: 'Mash',
			add_to_boil: 'Boil',
			add_to_fermentation: 'Fermentation',
			add_to_package: 'Packaging',
			primary: 'Primary',
			secondary: 'Secondary',
			bottling: 'Bottling',
		};
		const key = use.toLowerCase();
		return useMap[key] || (use ? use.charAt(0).toUpperCase() + use.slice(1) : '--');
	}

	function formatTime(misc: MiscIngredient): string {
		if (misc.time_min === undefined || misc.time_min === null) return '--';
		return `${misc.time_min.toFixed(0)}\u2009min`;
	}
</script>

{#if others.length > 0}
	<div class="other-ingredients">
		<h3>Other Ingredients</h3>
		<div class="table-scroll">
		<table>
			<thead>
				<tr>
					<th>Ingredient</th>
					<th>Type</th>
					<th>Use</th>
					<th class="num">Amount</th>
					<th class="num">Time</th>
				</tr>
			</thead>
			<tbody>
				{#each others as misc (misc.id)}
					<tr>
						<td class="name">
							{misc.name}
							{#if misc.use_for}
								<div class="use-for">{misc.use_for}</div>
							{/if}
						</td>
						<td class="type">{misc.type || '--'}</td>
						<td>{formatUse(misc)}</td>
						<td class="num">{formatAmount(misc)}</td>
						<td class="num">{formatTime(misc)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
		</div>
	</div>
{/if}

<style>
	h3 {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0 0 var(--space-sm) 0;
	}

	.table-scroll {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 480px;
		border-collapse: collapse;
	}

	th {
		text-align: left;
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-strong);
		font-size: var(--text-xs);
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
		white-space: nowrap;
	}

	td {
		padding: var(--space-xs) var(--space-sm);
		border-bottom: 1px solid var(--rule-hairline);
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}

	.num {
		text-align: right;
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}

	th.num {
		font-family: var(--font-body);
	}

	.name {
		font-weight: 600;
	}

	.use-for {
		color: var(--ink-muted);
		font-size: var(--text-xs);
		font-weight: 400;
		margin-top: 2px;
	}

	.type {
		color: var(--ink-secondary);
		text-transform: capitalize;
	}
</style>
