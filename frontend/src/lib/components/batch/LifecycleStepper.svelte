<script lang="ts">
	import type { BatchStatus } from '$lib/api';

	interface Props {
		currentStatus: BatchStatus;
	}

	let { currentStatus }: Props = $props();

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
				aria-current={state === 'current' ? 'step' : undefined}
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
	.lifecycle-stepper {
		width: 100%;
		padding: 0.5rem 0;
	}

	.stepper-track {
		display: flex;
		align-items: flex-start;
		list-style: none;
		margin: 0;
		padding: 0;
	}

	/* --- Connector lines between dots --- */
	.connector {
		flex: 1;
		height: 2px;
		background: var(--border-subtle);
		margin-top: 13px; /* vertically center with the 26px dot */
		transition: background 0.3s ease;
	}

	.connector.filled {
		background: var(--positive);
	}

	/* --- Step (dot + label) --- */
	.step {
		display: flex;
		flex-direction: column;
		align-items: center;
		flex-shrink: 0;
	}

	/* --- Dot --- */
	.dot {
		width: 26px;
		height: 26px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: all 0.3s ease;
		flex-shrink: 0;
	}

	.step.completed .dot {
		background: var(--positive);
		color: var(--bg-surface);
	}

	.step.current .dot {
		background: var(--accent);
		box-shadow: 0 0 0 4px var(--accent-muted);
		animation: pulse-dot 2.5s ease-in-out infinite;
	}

	.step.future .dot {
		background: var(--border-subtle);
	}

	.check-icon {
		width: 14px;
		height: 14px;
	}

	/* --- Label --- */
	.label {
		margin-top: 0.375rem;
		font-size: 0.6875rem;
		font-weight: 500;
		text-align: center;
		line-height: 1.2;
		white-space: nowrap;
		transition: color 0.3s ease;
	}

	.step.completed .label {
		color: var(--positive);
	}

	.step.current .label {
		color: var(--accent);
		font-weight: 600;
	}

	.step.future .label {
		color: var(--text-muted);
	}

	/* Show full labels by default, hide short ones */
	.short-label {
		display: none;
	}

	.full-label {
		display: block;
	}

	/* On narrow screens, swap to abbreviated labels */
	@media (max-width: 400px) {
		.short-label {
			display: block;
		}
		.full-label {
			display: none;
		}
	}

	/* --- Pulse animation for current dot --- */
	@keyframes pulse-dot {
		0%, 100% {
			box-shadow: 0 0 0 4px var(--accent-muted);
		}
		50% {
			box-shadow: 0 0 0 7px var(--accent-muted);
		}
	}
</style>
