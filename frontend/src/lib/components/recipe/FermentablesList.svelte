<script lang="ts">
	interface Fermentable {
		id: number;
		name: string;
		type?: string;
		amount_kg?: number;
		color_lovibond?: number;
		origin?: string;
		supplier?: string;
		yield_percent?: number;
	}

	let { fermentables }: { fermentables: Fermentable[] } = $props();

	// Calculate total and percentages
	let totalKg = $derived(
		fermentables.reduce((sum, f) => sum + (f.amount_kg || 0), 0)
	);

	function getPercent(amount?: number): string {
		if (!amount || !totalKg) return '--';
		return ((amount / totalKg) * 100).toFixed(1) + '%';
	}

	function formatKg(kg?: number): string {
		if (kg === undefined || kg === null) return '--';
		return kg.toFixed(2) + ' kg';
	}

	function formatColor(lovibond?: number): string {
		if (lovibond === undefined || lovibond === null) return '--';
		return lovibond.toFixed(0) + '°L';
	}
</script>

{#if fermentables.length > 0}
	<div class="fermentables">
		<h3>Grain Bill</h3>
		<table>
			<thead>
				<tr>
					<th>Fermentable</th>
					<th>Type</th>
					<th>Amount</th>
					<th>%</th>
					<th>Color</th>
				</tr>
			</thead>
			<tbody>
				{#each fermentables as ferm}
					<tr>
						<td class="name">
							{ferm.name}
							{#if ferm.origin}
								<span class="origin">({ferm.origin})</span>
							{/if}
							{#if ferm.supplier}
								<div class="supplier">{ferm.supplier}</div>
							{/if}
						</td>
						<td>{ferm.type || '--'}</td>
						<td>{formatKg(ferm.amount_kg)}</td>
						<td>{getPercent(ferm.amount_kg)}</td>
						<td>{formatColor(ferm.color_lovibond)}</td>
					</tr>
				{/each}
			</tbody>
			<tfoot>
				<tr>
					<td colspan="2"><strong>Total</strong></td>
					<td><strong>{formatKg(totalKg)}</strong></td>
					<td>100%</td>
					<td>--</td>
				</tr>
			</tfoot>
		</table>
	</div>
{/if}

<style>
	.fermentables {
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

	.origin {
		color: var(--text-muted);
		font-size: 13px;
		margin-left: var(--space-1);
	}

	.supplier {
		color: var(--text-muted);
		font-size: 12px;
		margin-top: var(--space-1);
	}

	tfoot td {
		border-top: 2px solid var(--border-default);
		border-bottom: none;
		padding-top: var(--space-3);
	}

	/* Responsive table */
	@media (max-width: 640px) {
		table {
			font-size: 12px;
		}

		th,
		td {
			padding: var(--space-2);
		}

		.supplier {
			display: none;
		}
	}
</style>
