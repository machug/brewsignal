<script lang="ts">
	interface MiscIngredient {
		id: number;
		name: string;
		type?: string;
		use?: string;
		amount_kg?: number;
		amount_unit?: string;
		timing?: {
			use?: string;
		};
	}

	interface WaterProfile {
		id: number;
		profile_type: string;
		name?: string;
		calcium_ppm?: number;
		magnesium_ppm?: number;
		sodium_ppm?: number;
		chloride_ppm?: number;
		sulfate_ppm?: number;
		bicarbonate_ppm?: number;
		ph?: number;
		alkalinity?: number;
	}

	interface WaterAdjustment {
		id: number;
		stage: string;
		volume_liters?: number;
		calcium_sulfate_g?: number;
		calcium_chloride_g?: number;
		magnesium_sulfate_g?: number;
		sodium_bicarbonate_g?: number;
		calcium_carbonate_g?: number;
		calcium_hydroxide_g?: number;
		magnesium_chloride_g?: number;
		sodium_chloride_g?: number;
		acid_type?: string;
		acid_ml?: number;
		acid_concentration_percent?: number;
	}

	let {
		miscs,
		waterProfiles = [],
		waterAdjustments = []
	}: {
		miscs: MiscIngredient[];
		waterProfiles?: WaterProfile[];
		waterAdjustments?: WaterAdjustment[];
	} = $props();

	// Get source and target profiles
	let sourceProfile = $derived(waterProfiles.find((p) => p.profile_type === 'source'));
	let targetProfile = $derived(waterProfiles.find((p) => p.profile_type === 'target'));
	let profileRows = $derived([
		{ label: 'Source', p: sourceProfile },
		{ label: 'Target', p: targetProfile }
	]);

	// Get mash and sparge adjustments. An adjustment row with no salts and
	// no acid (e.g. Brewfather sparge stage on a no-sparge profile) renders
	// as an empty box, so treat it as absent.
	function hasAdditions(adj: (typeof waterAdjustments)[number] | undefined): boolean {
		if (!adj) return false;
		return Boolean(
			adj.calcium_sulfate_g || adj.calcium_chloride_g || adj.magnesium_sulfate_g ||
			adj.sodium_bicarbonate_g || adj.sodium_chloride_g || adj.calcium_carbonate_g ||
			adj.calcium_hydroxide_g || adj.magnesium_chloride_g ||
			(adj.acid_type && adj.acid_ml)
		);
	}
	let mashAdjustment = $derived(
		[...waterAdjustments].filter((a) => a.stage === 'mash').find(hasAdditions)
	);
	let spargeAdjustment = $derived(
		[...waterAdjustments].filter((a) => a.stage === 'sparge').find(hasAdditions)
	);

	// Filter to only water agents
	let waterAgents = $derived(
		miscs.filter((m) => (m.type ?? '').toLowerCase().replace('_', ' ') === 'water agent')
	);

	// Group by use (mash vs sparge)
	let groupedAgents = $derived.by(() => {
		const groups: Record<string, MiscIngredient[]> = {
			mash: [],
			sparge: [],
			other: [],
		};

		for (const agent of waterAgents) {
			const use = agent.use?.toLowerCase() || agent.timing?.use?.toLowerCase() || '';
			if (use.includes('sparge')) {
				groups.sparge.push(agent);
			} else if (use.includes('mash') || use === 'add_to_mash') {
				groups.mash.push(agent);
			} else {
				groups.other.push(agent);
			}
		}

		return groups;
	});

	function formatAmount(agent: MiscIngredient): string {
		if (agent.amount_kg === undefined) return '--';
		const amount = agent.amount_kg;
		const unit = agent.amount_unit || 'g';
		// amount_kg is actually in the unit specified, not always kg
		return `${amount.toFixed(amount < 1 ? 2 : 1)}\u2009${unit}`;
	}

	function hasAgents(group: MiscIngredient[]): boolean {
		return group.length > 0;
	}
</script>

{#if waterAgents.length > 0 || waterProfiles.length > 0 || mashAdjustment || spargeAdjustment}
	<div class="water-additions">
		<h3 class="section-title">Water Chemistry</h3>

		<!-- Water Profiles (Source/Target) -->
		{#if sourceProfile || targetProfile}
			<div class="profiles-section">
				<h4 class="subsection-title">Water Profiles <span class="unit-note">ppm</span></h4>
				<div class="table-scroll">
					<table>
						<thead>
							<tr>
								<th>Profile</th>
								<th class="num">Ca</th>
								<th class="num">Mg</th>
								<th class="num">Na</th>
								<th class="num">Cl</th>
								<th class="num">SO4</th>
								<th class="num">HCO3</th>
								<th class="num">pH</th>
							</tr>
						</thead>
						<tbody>
							{#each profileRows as { label, p }}
								{#if p}
									<tr>
										<td class="name">{label}: {p.name || 'Untitled'}</td>
										<td class="num">{p.calcium_ppm?.toFixed(1) ?? '--'}</td>
										<td class="num">{p.magnesium_ppm?.toFixed(1) ?? '--'}</td>
										<td class="num">{p.sodium_ppm?.toFixed(1) ?? '--'}</td>
										<td class="num">{p.chloride_ppm?.toFixed(1) ?? '--'}</td>
										<td class="num">{p.sulfate_ppm?.toFixed(1) ?? '--'}</td>
										<td class="num">{p.bicarbonate_ppm?.toFixed(1) ?? '--'}</td>
										<td class="num">{p.ph ? p.ph.toFixed(1) : '--'}</td>
									</tr>
								{/if}
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{/if}

		<!-- Water Adjustments (structured salt data from Brewfather) -->
		{#if mashAdjustment || spargeAdjustment}
			<div class="adjustments-section">
				<h4 class="subsection-title">Calculated Additions</h4>
				<div class="additions-grid">
					{#if mashAdjustment}
						<div class="additions-group">
							<h4 class="group-title">Mash water treated ({mashAdjustment.volume_liters?.toFixed(1) ?? '--'}&thinsp;L)</h4>
							<ul class="additions-list">
								{#if mashAdjustment.calcium_sulfate_g}<li class="addition-item"><span class="addition-name">Gypsum (CaSO4)</span><span class="addition-amount">{mashAdjustment.calcium_sulfate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.calcium_chloride_g}<li class="addition-item"><span class="addition-name">Calcium Chloride</span><span class="addition-amount">{mashAdjustment.calcium_chloride_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.magnesium_sulfate_g}<li class="addition-item"><span class="addition-name">Epsom Salt (MgSO4)</span><span class="addition-amount">{mashAdjustment.magnesium_sulfate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.sodium_bicarbonate_g}<li class="addition-item"><span class="addition-name">Baking Soda</span><span class="addition-amount">{mashAdjustment.sodium_bicarbonate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.sodium_chloride_g}<li class="addition-item"><span class="addition-name">Table Salt (NaCl)</span><span class="addition-amount">{mashAdjustment.sodium_chloride_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.calcium_carbonate_g}<li class="addition-item"><span class="addition-name">Chalk (CaCO3)</span><span class="addition-amount">{mashAdjustment.calcium_carbonate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.calcium_hydroxide_g}<li class="addition-item"><span class="addition-name">Slaked Lime (Ca(OH)2)</span><span class="addition-amount">{mashAdjustment.calcium_hydroxide_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.magnesium_chloride_g}<li class="addition-item"><span class="addition-name">Magnesium Chloride (MgCl2)</span><span class="addition-amount">{mashAdjustment.magnesium_chloride_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if mashAdjustment.acid_type && mashAdjustment.acid_ml}<li class="addition-item"><span class="addition-name">{mashAdjustment.acid_type} acid ({mashAdjustment.acid_concentration_percent ?? '--'}%)</span><span class="addition-amount">{mashAdjustment.acid_ml.toFixed(2)}&thinsp;ml</span></li>{/if}
							</ul>
						</div>
					{/if}
					{#if spargeAdjustment}
						<div class="additions-group">
							<h4 class="group-title">Sparge water treated ({spargeAdjustment.volume_liters?.toFixed(1) ?? '--'}&thinsp;L)</h4>
							<ul class="additions-list">
								{#if spargeAdjustment.calcium_sulfate_g}<li class="addition-item"><span class="addition-name">Gypsum (CaSO4)</span><span class="addition-amount">{spargeAdjustment.calcium_sulfate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.calcium_chloride_g}<li class="addition-item"><span class="addition-name">Calcium Chloride</span><span class="addition-amount">{spargeAdjustment.calcium_chloride_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.magnesium_sulfate_g}<li class="addition-item"><span class="addition-name">Epsom Salt (MgSO4)</span><span class="addition-amount">{spargeAdjustment.magnesium_sulfate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.sodium_bicarbonate_g}<li class="addition-item"><span class="addition-name">Baking Soda</span><span class="addition-amount">{spargeAdjustment.sodium_bicarbonate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.sodium_chloride_g}<li class="addition-item"><span class="addition-name">Table Salt (NaCl)</span><span class="addition-amount">{spargeAdjustment.sodium_chloride_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.calcium_carbonate_g}<li class="addition-item"><span class="addition-name">Chalk (CaCO3)</span><span class="addition-amount">{spargeAdjustment.calcium_carbonate_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.calcium_hydroxide_g}<li class="addition-item"><span class="addition-name">Slaked Lime (Ca(OH)2)</span><span class="addition-amount">{spargeAdjustment.calcium_hydroxide_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.magnesium_chloride_g}<li class="addition-item"><span class="addition-name">Magnesium Chloride (MgCl2)</span><span class="addition-amount">{spargeAdjustment.magnesium_chloride_g.toFixed(2)}&thinsp;g</span></li>{/if}
								{#if spargeAdjustment.acid_type && spargeAdjustment.acid_ml}<li class="addition-item"><span class="addition-name">{spargeAdjustment.acid_type} acid ({spargeAdjustment.acid_concentration_percent ?? '--'}%)</span><span class="addition-amount">{spargeAdjustment.acid_ml.toFixed(2)}&thinsp;ml</span></li>{/if}
							</ul>
						</div>
					{/if}
				</div>
			</div>
		{/if}

		<!-- Legacy water agents from miscs (fallback) -->
		{#if waterAgents.length > 0}
			<div class="agents-section">
				<h4 class="subsection-title">Water Agents</h4>
				<div class="additions-grid">
					{#if hasAgents(groupedAgents.mash)}
						<div class="additions-group">
							<h4 class="group-title">Mash Additions</h4>
							<ul class="additions-list">
								{#each groupedAgents.mash as agent}
									<li class="addition-item">
										<span class="addition-name">{agent.name}</span>
										<span class="addition-amount">{formatAmount(agent)}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}

					{#if hasAgents(groupedAgents.sparge)}
						<div class="additions-group">
							<h4 class="group-title">Sparge Additions</h4>
							<ul class="additions-list">
								{#each groupedAgents.sparge as agent}
									<li class="addition-item">
										<span class="addition-name">{agent.name}</span>
										<span class="addition-amount">{formatAmount(agent)}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}

					{#if hasAgents(groupedAgents.other)}
						<div class="additions-group">
							<h4 class="group-title">Other Additions</h4>
							<ul class="additions-list">
								{#each groupedAgents.other as agent}
									<li class="addition-item">
										<span class="addition-name">{agent.name}</span>
										<span class="addition-amount">{formatAmount(agent)}</span>
									</li>
								{/each}
							</ul>
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>
{/if}

<style>
	.section-title {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-secondary);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin: 0 0 var(--space-sm) 0;
	}

	.profiles-section,
	.adjustments-section,
	.agents-section {
		margin-bottom: var(--space-md);
	}

	.profiles-section:last-child,
	.adjustments-section:last-child,
	.agents-section:last-child {
		margin-bottom: 0;
	}

	.subsection-title {
		font-family: var(--font-display);
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		margin: 0 0 var(--space-xs) 0;
	}

	.unit-note {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		font-weight: 400;
		color: var(--ink-muted);
		margin-left: var(--space-xs);
	}

	/* Profile table */
	.table-scroll {
		overflow-x: auto;
	}

	table {
		width: 100%;
		min-width: 520px;
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

	/* Additions: hairline ledger lists, side by side when there is room */
	.additions-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: var(--space-md) var(--space-lg);
	}

	.group-title {
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-strong);
	}

	.additions-list {
		list-style: none;
		margin: 0;
		padding: 0;
	}

	.addition-item {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-sm);
		padding: var(--space-xs) 0;
		border-bottom: 1px solid var(--rule-hairline);
	}

	.addition-name {
		font-size: var(--text-sm);
		color: var(--ink-primary);
	}

	.addition-amount {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		color: var(--ink-secondary);
		white-space: nowrap;
	}

	th:first-child,
	td:first-child {
		padding-left: 0;
	}

	th:last-child,
	td:last-child {
		padding-right: 0;
	}

	@media (max-width: 760px) {
		table {
			min-width: 0;
		}

		th,
		td {
			padding-inline: 3px;
			font-size: var(--text-xs);
			letter-spacing: 0;
		}

		th:first-child,
		td:first-child {
			padding-left: 0;
			white-space: normal;
		}

		th:last-child,
		td:last-child {
			padding-right: 0;
		}
	}
</style>
