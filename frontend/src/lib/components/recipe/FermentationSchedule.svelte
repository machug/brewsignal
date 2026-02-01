<script lang="ts">
	interface FermentationStep {
		id: number;
		step_number: number;
		type: string;
		temp_c: number;
		time_days: number;
	}

	let { steps }: { steps: FermentationStep[] } = $props();

	// Sort by step number
	let sortedSteps = $derived([...steps].sort((a, b) => a.step_number - b.step_number));

	function formatType(type: string): string {
		const typeMap: Record<string, string> = {
			primary: 'Primary',
			secondary: 'Secondary',
			conditioning: 'Conditioning',
			lagering: 'Lagering',
		};
		return typeMap[type.toLowerCase()] || type.charAt(0).toUpperCase() + type.slice(1);
	}

	function getTypeColor(type: string): string {
		const colorMap: Record<string, string> = {
			primary: 'var(--positive)',
			secondary: 'var(--info)',
			conditioning: 'var(--warning)',
			lagering: 'var(--info)',
		};
		return colorMap[type.toLowerCase()] || 'var(--text-muted)';
	}
</script>

{#if steps.length > 0}
	<div class="fermentation-schedule">
		<h3 class="section-title">
			<svg class="section-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
				<path stroke-linecap="round" stroke-linejoin="round" d="M19.428 15.428a2 2 0 00-1.022-.547l-2.387-.477a6 6 0 00-3.86.517l-.318.158a6 6 0 01-3.86.517L6.05 15.21a2 2 0 00-1.806.547M8 4h8l-1 1v5.172a2 2 0 00.586 1.414l5 5c1.26 1.26.367 3.414-1.415 3.414H4.828c-1.782 0-2.674-2.154-1.414-3.414l5-5A2 2 0 009 10.172V5L8 4z" />
			</svg>
			Fermentation Schedule
		</h3>
		<div class="steps-timeline">
			{#each sortedSteps as step, i}
				<div class="timeline-item">
					<div class="timeline-marker" style="background: {getTypeColor(step.type)}"></div>
					{#if i < sortedSteps.length - 1}
						<div class="timeline-connector"></div>
					{/if}
					<div class="timeline-content">
						<div class="step-header">
							<span class="step-type" style="color: {getTypeColor(step.type)}">{formatType(step.type)}</span>
						</div>
						<div class="step-stats">
							<div class="stat">
								<span class="stat-value">{step.temp_c.toFixed(0)}°C</span>
								<span class="stat-label">Temperature</span>
							</div>
							<div class="stat">
								<span class="stat-value">{step.time_days}</span>
								<span class="stat-label">{step.time_days === 1 ? 'Day' : 'Days'}</span>
							</div>
						</div>
					</div>
				</div>
			{/each}
		</div>
	</div>
{/if}

<style>
	.fermentation-schedule {
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

	.steps-timeline {
		display: flex;
		flex-direction: column;
	}

	.timeline-item {
		display: flex;
		gap: var(--space-3);
		position: relative;
		padding-bottom: var(--space-4);
	}

	.timeline-item:last-child {
		padding-bottom: 0;
	}

	.timeline-marker {
		width: 12px;
		height: 12px;
		border-radius: 50%;
		flex-shrink: 0;
		margin-top: 4px;
	}

	.timeline-connector {
		position: absolute;
		left: 5px;
		top: 20px;
		bottom: 0;
		width: 2px;
		background: var(--border-subtle);
	}

	.timeline-content {
		flex: 1;
		background: var(--bg-elevated);
		border-radius: 6px;
		padding: var(--space-3);
		border: 1px solid var(--border-subtle);
	}

	.step-header {
		margin-bottom: var(--space-2);
	}

	.step-type {
		font-weight: 600;
		font-size: 14px;
	}

	.step-stats {
		display: flex;
		gap: var(--space-6);
	}

	.stat {
		display: flex;
		flex-direction: column;
		gap: 2px;
	}

	.stat-value {
		font-family: var(--font-mono);
		font-size: 16px;
		font-weight: 500;
		color: var(--text-primary);
	}

	.stat-label {
		font-size: 11px;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.03em;
	}
</style>
