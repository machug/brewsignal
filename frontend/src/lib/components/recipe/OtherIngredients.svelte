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
		return `${misc.amount_kg.toFixed(misc.amount_kg < 1 ? 2 : 1)} ${unit}`;
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
		return `${misc.time_min.toFixed(0)} min`;
	}
</script>

{#if others.length > 0}
	<div class="other-ingredients">
		<h3>Other Ingredients</h3>
		<table>
			<thead>
				<tr>
					<th>Ingredient</th>
					<th>Type</th>
					<th>Use</th>
					<th>Amount</th>
					<th>Time</th>
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
						<td>{formatAmount(misc)}</td>
						<td>{formatTime(misc)}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{/if}

<style>
	.other-ingredients {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		padding: var(--space-4);
	}

	h3 {
		font-size: 16px;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 var(--space-4) 0;
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th {
		text-align: left;
		padding: var(--space-2) var(--space-3);
		border-bottom: 2px solid var(--border-default);
		font-size: 12px;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		font-weight: 600;
	}

	td {
		padding: var(--space-3);
		border-bottom: 1px solid var(--border-subtle);
		font-size: 14px;
		color: var(--text-primary);
	}

	tbody tr:last-child td {
		border-bottom: none;
	}

	.name {
		font-weight: 500;
	}

	.use-for {
		color: var(--text-muted);
		font-size: 12px;
		margin-top: var(--space-1);
	}

	.type {
		text-transform: capitalize;
	}

	@media (max-width: 640px) {
		table {
			font-size: 12px;
		}

		th,
		td {
			padding: var(--space-2);
		}

		.use-for {
			display: none;
		}
	}
</style>
