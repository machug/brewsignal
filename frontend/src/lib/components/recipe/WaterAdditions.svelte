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

	let { miscs }: { miscs: MiscIngredient[] } = $props();

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

{#if waterAgents.length > 0}
	<div class="water-additions">
		<h3 class="section-title">
			<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
			</svg>
			Water Chemistry
		</h3>

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
</style>
