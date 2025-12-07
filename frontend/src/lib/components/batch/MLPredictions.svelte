<script lang="ts">
	import { onMount } from 'svelte';
	import { formatGravity } from '$lib/stores/config.svelte';

	interface Props {
		batchId: number;
	}

	let { batchId }: Props = $props();

	interface MLPredictions {
		available: boolean;
		predicted_fg?: number;
		estimated_completion?: string;
		confidence?: number;
		data_quality?: number;
		num_readings?: number;
		error?: string;
	}

	let predictions = $state<MLPredictions>({ available: false });
	let loading = $state(true);

	onMount(async () => {
		try {
			const resp = await fetch(`/api/batches/${batchId}/predictions`);
			predictions = await resp.json();
		} catch (e) {
			console.error('Failed to load ML predictions:', e);
		} finally {
			loading = false;
		}
	});

	function formatDate(dateStr: string | undefined): string {
		if (!dateStr) return 'N/A';
		const date = new Date(dateStr);
		return date.toLocaleDateString('en-AU', { month: 'short', day: 'numeric', year: 'numeric' });
	}

	function daysRemaining(dateStr: string | undefined): number | null {
		if (!dateStr) return null;
		const target = new Date(dateStr);
		const now = new Date();
		const diff = target.getTime() - now.getTime();
		return Math.ceil(diff / (1000 * 60 * 60 * 24));
	}
</script>

{#if loading}
	<div class="ml-panel loading">
		<p>Loading predictions...</p>
	</div>
{:else if predictions.available}
	<div class="ml-panel">
		<h3 class="panel-title">ML Predictions</h3>

		<div class="metrics">
			{#if predictions.predicted_fg}
				<div class="metric">
					<span class="label">Predicted FG:</span>
					<span class="value">{formatGravity(predictions.predicted_fg)}</span>
				</div>
			{/if}

			{#if predictions.estimated_completion}
				{@const days = daysRemaining(predictions.estimated_completion)}
				<div class="metric">
					<span class="label">Est. Completion:</span>
					<span class="value">
						{formatDate(predictions.estimated_completion)}
						{#if days !== null}
							<span class="days">({days} {days === 1 ? 'day' : 'days'})</span>
						{/if}
					</span>
				</div>
			{/if}

			{#if predictions.confidence !== undefined}
				<div class="metric">
					<span class="label">Confidence:</span>
					<div class="progress-wrapper">
						<div class="progress-bar">
							<div class="fill" style="width: {predictions.confidence * 100}%"></div>
						</div>
						<span class="percentage">{(predictions.confidence * 100).toFixed(0)}%</span>
					</div>
				</div>
			{/if}

			{#if predictions.data_quality !== undefined}
				<div class="metric">
					<span class="label">Data Quality:</span>
					<div class="progress-wrapper">
						<div class="progress-bar">
							<div class="fill" style="width: {predictions.data_quality * 100}%"></div>
						</div>
						<span class="percentage">{(predictions.data_quality * 100).toFixed(0)}%</span>
					</div>
				</div>
			{/if}

			{#if predictions.num_readings}
				<div class="metric">
					<span class="label">Readings:</span>
					<span class="value">{predictions.num_readings} points</span>
				</div>
			{/if}
		</div>
	</div>
{:else}
	<div class="ml-panel disabled">
		<p class="unavailable-text">ML predictions unavailable (insufficient data)</p>
	</div>
{/if}

<style>
	.ml-panel {
		background: var(--surface-2);
		border: 1px solid var(--border-default);
		border-radius: 0.5rem;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	.ml-panel.loading,
	.ml-panel.disabled {
		text-align: center;
		padding: 2rem;
	}

	.panel-title {
		font-size: 0.875rem;
		font-weight: 600;
		margin-bottom: 1rem;
		color: var(--text-primary);
	}

	.metrics {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.metric {
		display: flex;
		justify-content: space-between;
		align-items: center;
		gap: 1rem;
	}

	.label {
		font-size: 0.8125rem;
		color: var(--text-secondary);
		font-family: 'JetBrains Mono', monospace;
	}

	.value {
		font-size: 0.8125rem;
		color: var(--text-primary);
		font-family: 'JetBrains Mono', monospace;
		font-weight: 500;
	}

	.days {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.progress-wrapper {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		flex: 1;
		max-width: 200px;
	}

	.progress-bar {
		flex: 1;
		height: 8px;
		background: var(--surface-3);
		border-radius: 4px;
		overflow: hidden;
	}

	.fill {
		height: 100%;
		background: linear-gradient(90deg, #10b981, #22c55e);
		transition: width 0.3s ease;
	}

	.percentage {
		font-size: 0.75rem;
		color: var(--text-secondary);
		font-family: 'JetBrains Mono', monospace;
		min-width: 3ch;
		text-align: right;
	}

	.unavailable-text {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}
</style>
