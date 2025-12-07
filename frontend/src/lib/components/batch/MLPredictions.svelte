<script lang="ts">
	import { onMount } from 'svelte';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { fetchBatchPredictions, reloadBatchPredictions, type MLPredictions } from '$lib/api';

	interface Props {
		batchId: number;
	}

	let { batchId }: Props = $props();

	let predictions = $state<MLPredictions>({ available: false });
	let loading = $state(true);
	let reloading = $state(false);
	let error = $state<string | null>(null);

	async function loadPredictions() {
		loading = true;
		error = null;
		try {
			predictions = await fetchBatchPredictions(batchId);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load predictions';
			console.error('Failed to load ML predictions:', e);
		} finally {
			loading = false;
		}
	}

	async function handleReload() {
		reloading = true;
		error = null;
		try {
			const result = await reloadBatchPredictions(batchId);
			console.log('Reloaded predictions:', result.message);
			// Refresh predictions after reload
			await loadPredictions();
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to reload predictions';
			console.error('Failed to reload predictions:', e);
		} finally {
			reloading = false;
		}
	}

	onMount(loadPredictions);

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
{:else if error}
	<div class="ml-panel error">
		<p class="error-text">⚠️ {error}</p>
	</div>
{:else if predictions.available}
	<div class="ml-panel">
		<div class="panel-header">
			<h3 class="panel-title">ML Predictions</h3>
			<button
				type="button"
				class="reload-btn"
				onclick={handleReload}
				disabled={reloading || loading}
				title="Recalculate predictions from database history"
			>
				{reloading ? 'Reloading...' : '↻ Reload'}
			</button>
		</div>

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

			{#if predictions.r_squared !== undefined}
				<div class="metric">
					<span class="label">Model Fit (R²):</span>
					<div class="progress-wrapper">
						<div class="progress-bar">
							<div class="fill" style="width: {predictions.r_squared * 100}%"></div>
						</div>
						<span class="percentage">{(predictions.r_squared * 100).toFixed(0)}%</span>
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
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 0.5rem;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	.ml-panel.loading,
	.ml-panel.disabled,
	.ml-panel.error {
		text-align: center;
		padding: 2rem;
	}

	.panel-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 1rem;
	}

	.panel-title {
		font-size: 0.875rem;
		font-weight: 600;
		margin: 0;
		color: var(--text-primary);
	}

	.reload-btn {
		padding: 0.25rem 0.5rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.25rem;
		cursor: pointer;
		transition: all 0.2s ease;
	}

	.reload-btn:hover:not(:disabled) {
		color: var(--text-primary);
		background: var(--bg-surface);
		border-color: var(--border-hover);
	}

	.reload-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
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
		font-family: var(--font-mono);
	}

	.value {
		font-size: 0.8125rem;
		color: var(--text-primary);
		font-family: var(--font-mono);
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
		background: var(--bg-elevated);
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
		font-family: var(--font-mono);
		min-width: 3ch;
		text-align: right;
	}

	.unavailable-text {
		color: var(--text-muted);
		font-size: 0.8125rem;
	}

	.error-text {
		color: var(--negative);
		font-size: 0.8125rem;
	}
</style>
