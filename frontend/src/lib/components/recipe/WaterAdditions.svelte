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

	// Get mash and sparge adjustments
	let mashAdjustment = $derived(waterAdjustments.find((a) => a.stage === 'mash'));
	let spargeAdjustment = $derived(waterAdjustments.find((a) => a.stage === 'sparge'));

	// Filter to only water agents
	let waterAgents = $derived(
		miscs.filter((m) => m.type?.toLowerCase() === 'water agent')
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
		return `${amount.toFixed(amount < 1 ? 2 : 1)} ${unit}`;
	}

	function hasAgents(group: MiscIngredient[]): boolean {
		return group.length > 0;
	}
</script>

{#if waterAgents.length > 0 || waterProfiles.length > 0 || waterAdjustments.length > 0}
	<div class="water-additions">
		<h3 class="section-title">
			<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
			</svg>
			Water Chemistry
		</h3>

		<!-- Water Profiles (Source/Target) -->
		{#if sourceProfile || targetProfile}
			<div class="profiles-section">
				<h4 class="subsection-title">Water Profiles</h4>
				<div class="profiles-grid">
					{#if sourceProfile}
						<div class="profile-card">
							<span class="profile-label">Source: {sourceProfile.name || 'Untitled'}</span>
							<div class="ion-grid">
								<div class="ion-item"><span class="ion-label">Ca</span><span class="ion-value">{sourceProfile.calcium_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">Mg</span><span class="ion-value">{sourceProfile.magnesium_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">Na</span><span class="ion-value">{sourceProfile.sodium_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">Cl</span><span class="ion-value">{sourceProfile.chloride_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">SO4</span><span class="ion-value">{sourceProfile.sulfate_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">HCO3</span><span class="ion-value">{sourceProfile.bicarbonate_ppm?.toFixed(1) ?? '--'}</span></div>
							</div>
							{#if sourceProfile.ph}
								<div class="profile-ph">pH: {sourceProfile.ph.toFixed(1)}</div>
							{/if}
						</div>
					{/if}
					{#if targetProfile}
						<div class="profile-card target">
							<span class="profile-label">Target: {targetProfile.name || 'Untitled'}</span>
							<div class="ion-grid">
								<div class="ion-item"><span class="ion-label">Ca</span><span class="ion-value">{targetProfile.calcium_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">Mg</span><span class="ion-value">{targetProfile.magnesium_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">Na</span><span class="ion-value">{targetProfile.sodium_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">Cl</span><span class="ion-value">{targetProfile.chloride_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">SO4</span><span class="ion-value">{targetProfile.sulfate_ppm?.toFixed(1) ?? '--'}</span></div>
								<div class="ion-item"><span class="ion-label">HCO3</span><span class="ion-value">{targetProfile.bicarbonate_ppm?.toFixed(1) ?? '--'}</span></div>
							</div>
							{#if targetProfile.ph}
								<div class="profile-ph">pH: {targetProfile.ph.toFixed(1)}</div>
							{/if}
						</div>
					{/if}
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
							<h4 class="group-title">Mash ({mashAdjustment.volume_liters?.toFixed(1) ?? '--'} L)</h4>
							<ul class="additions-list">
								{#if mashAdjustment.calcium_sulfate_g}<li class="addition-item"><span class="addition-name">Gypsum (CaSO4)</span><span class="addition-amount">{mashAdjustment.calcium_sulfate_g.toFixed(2)} g</span></li>{/if}
								{#if mashAdjustment.calcium_chloride_g}<li class="addition-item"><span class="addition-name">Calcium Chloride</span><span class="addition-amount">{mashAdjustment.calcium_chloride_g.toFixed(2)} g</span></li>{/if}
								{#if mashAdjustment.magnesium_sulfate_g}<li class="addition-item"><span class="addition-name">Epsom Salt (MgSO4)</span><span class="addition-amount">{mashAdjustment.magnesium_sulfate_g.toFixed(2)} g</span></li>{/if}
								{#if mashAdjustment.sodium_bicarbonate_g}<li class="addition-item"><span class="addition-name">Baking Soda</span><span class="addition-amount">{mashAdjustment.sodium_bicarbonate_g.toFixed(2)} g</span></li>{/if}
								{#if mashAdjustment.sodium_chloride_g}<li class="addition-item"><span class="addition-name">Table Salt (NaCl)</span><span class="addition-amount">{mashAdjustment.sodium_chloride_g.toFixed(2)} g</span></li>{/if}
								{#if mashAdjustment.calcium_carbonate_g}<li class="addition-item"><span class="addition-name">Chalk (CaCO3)</span><span class="addition-amount">{mashAdjustment.calcium_carbonate_g.toFixed(2)} g</span></li>{/if}
								{#if mashAdjustment.acid_type && mashAdjustment.acid_ml}<li class="addition-item"><span class="addition-name">{mashAdjustment.acid_type} acid ({mashAdjustment.acid_concentration_percent ?? '--'}%)</span><span class="addition-amount">{mashAdjustment.acid_ml.toFixed(2)} ml</span></li>{/if}
							</ul>
						</div>
					{/if}
					{#if spargeAdjustment}
						<div class="additions-group">
							<h4 class="group-title">Sparge ({spargeAdjustment.volume_liters?.toFixed(1) ?? '--'} L)</h4>
							<ul class="additions-list">
								{#if spargeAdjustment.calcium_sulfate_g}<li class="addition-item"><span class="addition-name">Gypsum (CaSO4)</span><span class="addition-amount">{spargeAdjustment.calcium_sulfate_g.toFixed(2)} g</span></li>{/if}
								{#if spargeAdjustment.calcium_chloride_g}<li class="addition-item"><span class="addition-name">Calcium Chloride</span><span class="addition-amount">{spargeAdjustment.calcium_chloride_g.toFixed(2)} g</span></li>{/if}
								{#if spargeAdjustment.magnesium_sulfate_g}<li class="addition-item"><span class="addition-name">Epsom Salt (MgSO4)</span><span class="addition-amount">{spargeAdjustment.magnesium_sulfate_g.toFixed(2)} g</span></li>{/if}
								{#if spargeAdjustment.sodium_bicarbonate_g}<li class="addition-item"><span class="addition-name">Baking Soda</span><span class="addition-amount">{spargeAdjustment.sodium_bicarbonate_g.toFixed(2)} g</span></li>{/if}
								{#if spargeAdjustment.sodium_chloride_g}<li class="addition-item"><span class="addition-name">Table Salt (NaCl)</span><span class="addition-amount">{spargeAdjustment.sodium_chloride_g.toFixed(2)} g</span></li>{/if}
								{#if spargeAdjustment.calcium_carbonate_g}<li class="addition-item"><span class="addition-name">Chalk (CaCO3)</span><span class="addition-amount">{spargeAdjustment.calcium_carbonate_g.toFixed(2)} g</span></li>{/if}
								{#if spargeAdjustment.acid_type && spargeAdjustment.acid_ml}<li class="addition-item"><span class="addition-name">{spargeAdjustment.acid_type} acid ({spargeAdjustment.acid_concentration_percent ?? '--'}%)</span><span class="addition-amount">{spargeAdjustment.acid_ml.toFixed(2)} ml</span></li>{/if}
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
	.water-additions {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 6px;
		padding: var(--space-4);
	}

	.section-title {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		font-size: 14px;
		font-weight: 600;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 var(--space-4) 0;
	}

	.section-icon {
		width: 18px;
		height: 18px;
		opacity: 0.8;
	}

	.additions-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
		gap: var(--space-4);
	}

	.additions-group {
		background: var(--bg-elevated);
		border-radius: 6px;
		padding: var(--space-3);
		border: 1px solid var(--border-subtle);
	}

	.group-title {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 var(--space-3) 0;
		padding-bottom: var(--space-2);
		border-bottom: 1px solid var(--border-subtle);
	}

	.additions-list {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
		gap: var(--space-2);
	}

	.addition-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: var(--space-2);
	}

	.addition-name {
		font-size: 13px;
		color: var(--text-primary);
	}

	.addition-amount {
		font-family: var(--font-mono);
		font-size: 13px;
		color: var(--text-secondary);
		white-space: nowrap;
	}

	/* Subsection styling */
	.profiles-section,
	.adjustments-section,
	.agents-section {
		margin-bottom: var(--space-4);
	}

	.profiles-section:last-child,
	.adjustments-section:last-child,
	.agents-section:last-child {
		margin-bottom: 0;
	}

	.subsection-title {
		font-size: 12px;
		font-weight: 600;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.05em;
		margin: 0 0 var(--space-3) 0;
	}

	/* Water Profiles Grid */
	.profiles-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
		gap: var(--space-3);
	}

	.profile-card {
		background: var(--bg-elevated);
		border-radius: 6px;
		padding: var(--space-3);
		border: 1px solid var(--border-subtle);
	}

	.profile-card.target {
		border-color: var(--recipe-accent-border);
		background: linear-gradient(135deg, var(--bg-elevated) 0%, rgba(245, 158, 11, 0.03) 100%);
	}

	.profile-label {
		display: block;
		font-size: 12px;
		font-weight: 600;
		color: var(--text-secondary);
		margin-bottom: var(--space-2);
	}

	.ion-grid {
		display: grid;
		grid-template-columns: repeat(3, 1fr);
		gap: var(--space-1);
	}

	.ion-item {
		display: flex;
		justify-content: space-between;
		padding: 2px 4px;
		background: var(--bg-surface);
		border-radius: 3px;
	}

	.ion-label {
		font-size: 11px;
		font-weight: 500;
		color: var(--text-muted);
	}

	.ion-value {
		font-family: var(--font-mono);
		font-size: 11px;
		color: var(--text-primary);
	}

	.profile-ph {
		margin-top: var(--space-2);
		font-family: var(--font-mono);
		font-size: 12px;
		color: var(--text-secondary);
	}
</style>
