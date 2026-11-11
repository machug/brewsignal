<script lang="ts">
	interface Fermentable {
		id: number;
		name: string;
		type?: string;
		amount_kg?: number;
		color_srm?: number;  // API returns SRM
		color_lovibond?: number;  // Legacy/alternate format
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
		return ((amount / totalKg) * 100).toFixed(1) + ' %';
	}

	function formatKg(kg?: number): string {
		if (kg === undefined || kg === null) return '--';
		return kg.toFixed(2) + ' kg';
	}

	function formatColor(ferm: Fermentable): string {
		// Prefer SRM (what API returns), fallback to Lovibond
		const srm = ferm.color_srm;
		const lovibond = ferm.color_lovibond;
		if (srm !== undefined && srm !== null) {
			return srm.toFixed(0) + ' SRM';
		}
		if (lovibond !== undefined && lovibond !== null) {
			return lovibond.toFixed(0) + ' °L';
		}
		return '--';
	}
</script>

{#if fermentables.length > 0}
	<div class="fermentables">
		<h3>Grain Bill</h3>
		<div class="table-scroll">
			<table>
				<thead>
					<tr>
						<th>Fermentable</th>
						<th>Type</th>
						<th class="num">Amount</th>
						<th class="num">%</th>
						<th class="num">Color</th>
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
							<td class="type">{ferm.type || '--'}</td>
							<td class="num">{formatKg(ferm.amount_kg)}</td>
							<td class="num">{getPercent(ferm.amount_kg)}</td>
							<td class="num">{formatColor(ferm)}</td>
						</tr>
					{/each}
				</tbody>
				<tfoot>
					<tr>
						<td colspan="2">Total</td>
						<td class="num">{formatKg(totalKg)}</td>
						<td class="num">100&thinsp;%</td>
						<td class="num">--</td>
					</tr>
				</tfoot>
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

	.type {
		color: var(--ink-secondary);
		text-transform: capitalize;
	}

	.origin {
		color: var(--ink-muted);
		font-weight: 400;
		margin-left: var(--space-2xs);
	}

	.supplier {
		color: var(--ink-muted);
		font-size: var(--text-xs);
		font-weight: 400;
		margin-top: 2px;
	}

	tfoot td {
		border-top: 1px solid var(--rule-strong);
		border-bottom: none;
		color: var(--ink-secondary);
		font-size: var(--text-xs);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		font-weight: 600;
	}

	tfoot td.num {
		font-size: var(--text-sm);
		color: var(--ink-primary);
		text-transform: none;
		letter-spacing: 0;
	}
</style>
