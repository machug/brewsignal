<script lang="ts">
	interface MashStep {
		id: number;
		step_number: number;
		name: string;
		type: string;
		temp_c: number;
		time_minutes: number;
		ramp_time_minutes?: number;
	}

	let { steps }: { steps: MashStep[] } = $props();

	// Sort by step number
	let sortedSteps = $derived([...steps].sort((a, b) => a.step_number - b.step_number));

	function formatType(type: string): string {
		const typeMap: Record<string, string> = {
			temperature: 'Temperature',
			infusion: 'Infusion',
			decoction: 'Decoction',
		};
		return typeMap[type.toLowerCase()] || type;
	}
</script>

{#if steps.length > 0}
	<div class="mash-schedule">
		<h3 class="section-title">
			<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M17.657 18.657A8 8 0 016.343 7.343S7 9 9 10c0-2 .5-5 2.986-7C14 5 16.09 5.777 17.656 7.343A7.975 7.975 0 0120 13a7.975 7.975 0 01-2.343 5.657z" />
			</svg>
			Mash Schedule
		</h3>
		<div class="steps-list">
			{#each sortedSteps as step, i}
				<div class="step-item">
					<div class="step-number">{i + 1}</div>
					<div class="step-content">
						<div class="step-header">
							<span class="step-name">{step.name}</span>
							<span class="step-type">{formatType(step.type)}</span>
						</div>
						<div class="step-details">
							<span class="detail">
								<span class="detail-value">{step.temp_c.toFixed(0)}°C</span>
							</span>
							<span class="detail">
								<span class="detail-value">{step.time_minutes} min</span>
							</span>
							{#if step.ramp_time_minutes}
								<span class="detail ramp">
									<span class="detail-label">Ramp:</span>
									<span class="detail-value">{step.ramp_time_minutes} min</span>
								</span>
							{/if}
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}

<style>
	.mash-schedule {
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

	.steps-list {
		display: flex;
		flex-direction: column;
		gap: var(--space-3);
	}

	.step-item {
		display: flex;
		gap: var(--space-3);
		padding: var(--space-3);
		background: var(--bg-elevated);
		border-radius: 6px;
		border: 1px solid var(--border-subtle);
	}

	.step-number {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 28px;
		height: 28px;
		background: var(--recipe-accent);
		color: var(--gray-950);
		border-radius: 50%;
		font-size: 13px;
		font-weight: 600;
		flex-shrink: 0;
	}

	.step-content {
		flex: 1;
		min-width: 0;
	}

	.step-header {
		display: flex;
		align-items: center;
		gap: var(--space-2);
		margin-bottom: var(--space-2);
	}

	.step-name {
		font-weight: 500;
		color: var(--text-primary);
	}

	.step-type {
		font-size: 12px;
		color: var(--text-muted);
		padding: 2px 6px;
		background: var(--bg-surface);
		border-radius: 4px;
	}

	.step-details {
		display: flex;
		gap: var(--space-4);
		flex-wrap: wrap;
	}

	.detail {
		display: flex;
		align-items: center;
		gap: var(--space-1);
	}

	.detail-label {
		font-size: 12px;
		color: var(--text-muted);
	}

	.detail-value {
		font-family: var(--font-mono);
		font-size: 14px;
		color: var(--text-primary);
	}

	.ramp {
		color: var(--text-secondary);
	}
</style>
