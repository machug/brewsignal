<script lang="ts">
	import type { BatchStatus } from '$lib/api';

	interface Props {
		currentStatus: BatchStatus;
		onPhaseClick?: (status: BatchStatus) => void;
	}

	let { currentStatus, onPhaseClick }: Props = $props();

	const phases: { label: string; shortLabel: string; status: BatchStatus }[] = [
		{ label: 'Recipe', shortLabel: 'Recipe', status: 'planning' },
		{ label: 'Brew Day', shortLabel: 'Brew', status: 'brewing' },
		{ label: 'Fermentation', shortLabel: 'Ferm', status: 'fermenting' },
		{ label: 'Conditioning', shortLabel: 'Cond', status: 'conditioning' },
		{ label: 'Complete', shortLabel: 'Done', status: 'completed' }
	];

	const statusOrder: Record<BatchStatus, number> = {
		planning: 0,
		brewing: 1,
		fermenting: 2,
		conditioning: 3,
		completed: 4,
		archived: 4
	};

	let currentIndex = $derived(statusOrder[currentStatus] ?? 0);

	function phaseState(phaseIndex: number): 'completed' | 'current' | 'future' {
		if (phaseIndex < currentIndex) return 'completed';
		if (phaseIndex === currentIndex) return 'current';
		return 'future';
	}
</script>

<nav class="lifecycle-stepper" aria-label="Batch lifecycle progress">
	<ol class="stepper-track">
		{#each phases as phase, i}
			{@const state = phaseState(i)}

			{#if i > 0}
				<li class="connector" class:filled={i <= currentIndex} aria-hidden="true"></li>
			{/if}

			<li
				class="step"
				class:completed={state === 'completed'}
				class:current={state === 'current'}
				class:future={state === 'future'}
				class:clickable={state !== 'future' && !!onPhaseClick}
				aria-current={state === 'current' ? 'step' : undefined}
				onclick={() => state !== 'future' && onPhaseClick?.(phase.status)}
				onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && state !== 'future' && onPhaseClick?.(phase.status)}
				role={onPhaseClick ? 'button' : undefined}
				tabindex={state !== 'future' && onPhaseClick ? 0 : undefined}
			>
				<div class="dot">
					{#if state === 'completed'}
						<svg
							class="check-icon"
							viewBox="0 0 16 16"
							fill="none"
							aria-hidden="true"
						>
							<path
								d="M3.5 8.5L6.5 11.5L12.5 5.5"
								stroke="currentColor"
								stroke-width="2"
								stroke-linecap="round"
								stroke-linejoin="round"
							/>
						</svg>
					{/if}
				</div>
				<span class="label full-label">{phase.label}</span>
				<span class="label short-label">{phase.shortLabel}</span>
			</li>
		{/each}
	</ol>
</nav>

<style>
	/* Calm hairline step track: done = ink, current = accent, future = muted */
	.lifecycle-stepper {
		width: 100%;
		padding: var(--space-xs) 0;
	}
	.stepper-track {
		display: flex;
		align-items: flex-start;
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.connector {
		flex: 1;
		height: 1px;
		background: var(--rule-hairline);
		margin-top: 12px;
	}
	.connector.filled {
		background: var(--ink-secondary);
	}
	.step {
		display: flex;
		flex-direction: column;
		align-items: center;
		flex-shrink: 0;
		min-width: 44px;
	}
	.step.clickable {
		cursor: pointer;
	}
	.dot {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		border: 1px solid var(--rule-strong);
		background: var(--bg-canvas);
	}
	.step.completed .dot {
		border-color: var(--ink-secondary);
		color: var(--ink-primary);
	}
	.step.current .dot {
		border-color: var(--accent);
		background: var(--accent);
		color: var(--accent-ink);
	}
	.step.future .dot {
		border-color: var(--rule-hairline);
	}
	.step.clickable:hover .dot {
		border-color: var(--ink-primary);
	}
	.check-icon {
		width: 14px;
		height: 14px;
	}
	.label {
		margin-top: var(--space-2xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-align: center;
		line-height: 1.2;
		white-space: nowrap;
	}
	.step.completed .label {
		color: var(--ink-primary);
	}
	.step.current .label {
		color: var(--accent);
	}
	.step.future .label {
		color: var(--ink-muted);
	}
	.short-label {
		display: none;
	}
	.full-label {
		display: block;
	}
	@media (max-width: 400px) {
		.short-label {
			display: block;
		}
		.full-label {
			display: none;
		}
	}
</style>
