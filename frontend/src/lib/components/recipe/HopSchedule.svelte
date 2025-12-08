<script lang="ts">
	interface Hop {
		id: number;
		name: string;
		origin?: string;
		form?: string;
		alpha_acid_percent?: number;
		beta_acid_percent?: number;
		amount_grams?: number;
		timing?: {
			use?: string;
			duration?: {
				value?: number;
				unit?: string;
			};
		};
	}

	let { hops }: { hops: Hop[] } = $props();

	// Group hops by use (Boil, Dry Hop, etc.)
	let groupedHops = $derived.by(() => {
		const groups: Record<string, Hop[]> = {};
		for (const hop of hops) {
			const use = hop.timing?.use || 'Other';
			if (!groups[use]) groups[use] = [];
			groups[use].push(hop);
		}
		// Sort boil hops by time (longest first)
		for (const [use, hopList] of Object.entries(groups)) {
			if (use === 'add_to_boil' || use === 'Boil') {
				hopList.sort((a, b) => (b.timing?.duration?.value || 0) - (a.timing?.duration?.value || 0));
			}
		}
		return groups;
	});

	function formatAmount(grams?: number): string {
		if (grams === undefined || grams === null) return '--';
		return grams.toFixed(0) + 'g';
	}

	function formatAlpha(percent?: number): string {
		if (percent === undefined || percent === null) return '--';
		return percent.toFixed(1) + '%';
	}

	function formatTime(timing?: { use?: string; duration?: { value?: number; unit?: string } }): string {
		if (!timing?.duration?.value) return '--';
		const value = timing.duration.value;
		const use = timing.use;

		if (use === 'dry_hop') {
			return value === 0 ? 'At packaging' : `Day ${value}`;
		}
		return `${value} ${timing.duration.unit || 'min'}`;
	}

	function formatUse(use?: string): string {
		if (!use) return 'Other';
		// Convert BeerJSON format to readable names
		const useMap: Record<string, string> = {
			'add_to_boil': 'Boil',
			'dry_hop': 'Dry Hop',
			'whirlpool': 'Whirlpool',
			'first_wort': 'First Wort',
			'mash': 'Mash',
			'aroma': 'Aroma'
		};
		return useMap[use] || use;
	}
</script>

{#if hops.length > 0}
	<div class="hop-schedule">
		<h3>Hop Schedule</h3>

		{#each Object.entries(groupedHops) as [use, hopList]}
			<div class="hop-group">
				<h4>{formatUse(use)}</h4>
				<table>
					<thead>
						<tr>
							<th>Hop</th>
							<th>Amount</th>
							<th>AA%</th>
							<th>Time</th>
							<th>Form</th>
						</tr>
					</thead>
					<tbody>
						{#each hopList as hop}
							<tr>
								<td class="hop-name">
									{hop.name}
									{#if hop.origin}
										<div class="hop-type">{hop.origin}</div>
									{/if}
								</td>
								<td>{formatAmount(hop.amount_grams)}</td>
								<td>{formatAlpha(hop.alpha_acid_percent)}</td>
								<td>{formatTime(hop.timing)}</td>
								<td>{hop.form || '--'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/each}
	</div>
{/if}

<style>
	.hop-schedule {
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

	.hop-group {
		margin-bottom: var(--space-4);
	}

	.hop-group:last-child {
		margin-bottom: 0;
	}

	h4 {
		font-size: 13px;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: var(--space-3);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	table {
		width: 100%;
		border-collapse: collapse;
	}

	th {
		text-align: left;
		padding: var(--space-2) var(--space-3);
		font-size: 12px;
		color: var(--text-muted);
		font-weight: 500;
	}

	td {
		padding: var(--space-2) var(--space-3);
		font-size: 14px;
		color: var(--text-primary);
	}

	tbody tr {
		border-bottom: 1px solid var(--border-subtle);
	}

	tbody tr:last-child {
		border-bottom: none;
	}

	.hop-name {
		font-weight: 500;
	}

	.hop-type {
		color: var(--text-muted);
		font-size: 12px;
		margin-top: var(--space-1);
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

		.hop-type {
			display: none;
		}
	}
</style>
