<script lang="ts">
	interface Hop {
		// id is only populated for recipe_hops rows; UI-editor hops merged
		// in via format_extensions omit it. Tolerate both.
		id?: number;
		name: string;
		origin?: string | null;
		form?: string | null;
		alpha_acid_percent?: number | null;
		beta_acid_percent?: number | null;
		amount_grams?: number | null;
		// Abstrax-style extract semantics (tilt_ui-0l5).
		amount_ml?: number | null;
		is_extract?: boolean;
		timing?: {
			use?: string;
			// BeerJSON uses 'duration', but some sources use 'time'
			duration?: {
				value?: number;
				unit?: string;
			};
			time?: {
				value?: number;
				unit?: string;
			};
			temperature?: {
				value?: number;
				unit?: string;
			};
		};
	}

	let { hops }: { hops: Hop[] } = $props();

	// Helper to get timing value (handles both 'duration' and 'time' keys)
	function getTimingValue(timing?: Hop['timing']): number | undefined {
		return timing?.duration?.value ?? timing?.time?.value;
	}

	function getTimingUnit(timing?: Hop['timing']): string | undefined {
		return timing?.duration?.unit ?? timing?.time?.unit;
	}

	// Brew-day order for groups: whirlpool happens after the boil ends, so
	// it must follow the boil group whatever its stand time (tilt_ui-2mxj).
	// Unlisted uses (fermentation, package, ...) keep their order after these.
	const HOT_SIDE_ORDER = ['add_to_mash', 'mash', 'first_wort', 'add_to_boil', 'boil', 'whirlpool', 'add_to_whirlpool'];
	function groupRank(use: string): number {
		const i = HOT_SIDE_ORDER.indexOf(use.toLowerCase());
		return i === -1 ? HOT_SIDE_ORDER.length : i;
	}

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
			if (use === 'add_to_boil' || use === 'Boil' || use === 'boil') {
				hopList.sort((a, b) => (getTimingValue(b.timing) || 0) - (getTimingValue(a.timing) || 0));
			}
		}
		return Object.entries(groups).sort(([a], [b]) => groupRank(a) - groupRank(b));
	});

	function formatAmount(grams?: number | null): string {
		if (grams === undefined || grams === null) return '--';
		return grams.toFixed(0) + '\u2009g';
	}

	function formatAlpha(percent?: number | null): string {
		if (percent === undefined || percent === null) return '--';
		return percent.toFixed(1) + '%';
	}

	function formatTime(timing?: Hop['timing']): string {
		const value = getTimingValue(timing);
		if (value === undefined) return '--';
		const unit = getTimingUnit(timing) || 'min';
		const use = timing?.use;

		// Dry hop and fermentation additions use day-based timing
		if (use === 'dry_hop' || use === 'dry hop' || use === 'add_to_fermentation') {
			if (value === 0) return 'At packaging';
			// Editor saves store the dry hop day count as minutes (3 days =
			// 4320 min); show it in days like imported rows (tilt_ui-5z86)
			return unit === 'min' ? `${+(value / (24 * 60)).toFixed(2)}\u2009day` : `${value}\u2009${unit}`;
		}
		// Whirlpool - show time and temperature if available
		const isWhirlpool = use === 'whirlpool' || use === 'Whirlpool' || use === 'add_to_whirlpool';
		if (isWhirlpool && timing?.temperature?.value) {
			return `${value}\u2009${unit} @ ${timing.temperature.value}\u2009°${timing.temperature.unit || 'C'}`;
		}
		return `${value}\u2009${unit}`;
	}

	function formatUse(use?: string): string {
		if (!use) return 'Other';
		// Normalize to lowercase for consistent lookup
		const normalized = use.toLowerCase().replace(/\s+/g, '_');
		// Convert BeerJSON format to readable names
		const useMap: Record<string, string> = {
			'add_to_boil': 'Boil',
			'boil': 'Boil',
			'dry_hop': 'Dry Hop',
			'add_to_fermentation': 'Fermentation',
			'whirlpool': 'Whirlpool',
			'add_to_whirlpool': 'Whirlpool',
			'first_wort': 'First Wort',
			'mash': 'Mash',
			'aroma': 'Aroma'
		};
		// Gracefully handle unknown timing keys by converting snake_case to Title Case
		return useMap[normalized] || use.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
	}
</script>

{#if hops.length > 0}
	<div class="hop-schedule">
		<h3>Hop Schedule</h3>

		{#each groupedHops as [use, hopList]}
			<div class="hop-group">
				<h4>{formatUse(use)}</h4>
				<div class="table-scroll">
				<table>
					<thead>
						<tr>
							<th>Hop</th>
							<th class="num">Amount</th>
							<th class="num">AA</th>
							<th class="num">Time</th>
							<th class="col-sec">Form</th>
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
									{#if hop.is_extract}
										<div class="hop-type">Aroma-only · no IBU</div>
									{/if}
									<div class="sec-inline">{hop.is_extract ? 'Extract' : hop.form || 'Pellet'}</div>
								</td>
								<td class="num">
									{#if hop.is_extract}
										{hop.amount_ml != null ? `${hop.amount_ml.toFixed(1)}\u2009mL` : '--'}
									{:else}
										{formatAmount(hop.amount_grams)}
									{/if}
								</td>
								<td class="num">{hop.is_extract ? '—' : formatAlpha(hop.alpha_acid_percent)}</td>
								<td class="num">{formatTime(hop.timing)}</td>
								<td class="form col-sec">{hop.is_extract ? 'Extract' : hop.form || 'Pellet'}</td>
							</tr>
						{/each}
					</tbody>
				</table>
				</div>
			</div>
		{/each}
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

	.hop-group {
		margin-bottom: var(--space-md);
	}

	.hop-group:last-child {
		margin-bottom: 0;
	}

	/* Use-group label (Boil, Dry Hop...) */
	h4 {
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0 0 var(--space-2xs) 0;
	}

	.table-scroll {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 560px;
		border-collapse: collapse;
		table-layout: fixed;
	}

	th:nth-child(2) { width: 88px; }
	th:nth-child(3) { width: 72px; }
	th:nth-child(4) { width: 150px; }
	th:nth-child(5) { width: 96px; }

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

	.hop-name {
		font-weight: 600;
	}

	.hop-type {
		color: var(--ink-muted);
		font-size: var(--text-xs);
		font-weight: 400;
		margin-top: 2px;
	}

	.form {
		color: var(--ink-secondary);
		text-transform: capitalize;
	}

	th:first-child,
	td:first-child {
		padding-left: 0;
	}

	th:last-child,
	td:last-child {
		padding-right: 0;
	}

	.sec-inline {
		display: none;
		color: var(--ink-muted);
		font-size: var(--text-xs);
		font-weight: 400;
		margin-top: 2px;
		text-transform: capitalize;
	}

	@media (max-width: 760px) {
		table {
			min-width: 0;
			table-layout: auto;
		}

		.col-sec {
			display: none;
		}

		.sec-inline {
			display: block;
		}

		th,
		td {
			padding-inline: var(--space-xs);
		}

		th:first-child,
		td:first-child {
			padding-left: 0;
		}

		th:last-child,
		td:last-child {
			padding-right: 0;
		}

		/* Fixed layout: tighter numeric columns, time may wrap */
		table {
			table-layout: fixed;
		}

		th:nth-child(2) { width: 56px; }
		th:nth-child(3) { width: 52px; }
		th:nth-child(4) { width: 92px; }

		td.num {
			white-space: normal;
		}
	}
</style>
