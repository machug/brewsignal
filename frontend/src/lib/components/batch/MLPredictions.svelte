<script lang="ts">
	import { onMount } from 'svelte';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { fetchBatchPredictions, reloadBatchPredictions, type MLPredictions } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';

	interface Props {
		batchId: number;
		batchStatus?: string;
		measuredOg?: number | null;
		measuredFg?: number | null;  // Actual FG from batch (after completion)
		recipeFg?: number | null;  // Recipe target FG (for progress calculation)
		currentSg?: number | null;
		liveReading?: TiltReading | null;
	}

	let { batchId, batchStatus = 'fermenting', measuredOg = null, measuredFg = null, recipeFg = null, currentSg = null, liveReading = null }: Props = $props();

	let predictions = $state<MLPredictions>({ available: false });
	let loading = $state(true);
	let reloading = $state(false);
	let error = $state<string | null>(null);

	// Model selection
	let selectedModel = $state('auto');
	const models = [
		{ value: 'auto', label: 'Auto (Best Fit)' },
		{ value: 'exponential', label: 'Exponential' },
		{ value: 'gompertz', label: 'Gompertz (S-Curve)' },
		{ value: 'logistic', label: 'Logistic' }
	];

	// Check if batch is completed
	let isCompleted = $derived(batchStatus === 'completed' || batchStatus === 'archived');

	// Get the actual final gravity (from batch or current reading)
	let actualFg = $derived(measuredFg ?? currentSg);

	// Calculate prediction accuracy for completed batches
	let predictionAccuracy = $derived.by(() => {
		if (!isCompleted || !predictions.predicted_fg || !actualFg) return null;
		const diff = Math.abs(predictions.predicted_fg - actualFg);
		const points = Math.round(diff * 1000); // Convert to gravity points
		return {
			diff: diff,
			points: points,
			isAccurate: points <= 2, // Within 2 points is accurate
			isClose: points <= 5,    // Within 5 points is close
		};
	});

	async function loadPredictions() {
		loading = true;
		error = null;
		try {
			predictions = await fetchBatchPredictions(batchId, selectedModel);
		} catch (e) {
			error = e instanceof Error ? e.message : 'Failed to load predictions';
			console.error('Failed to load ML predictions:', e);
		} finally {
			loading = false;
		}
	}

	async function handleReload() {
		reloading = true;
		loading = true;
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
			loading = false;
		}
	}

	// Handle model change
	function handleModelChange() {
		loadPredictions();
	}

	// Always reload fresh predictions on mount
	onMount(handleReload);

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

	// Detect potential stuck fermentation (predicted FG differs from recipe target)
	let stuckFermentationWarning = $derived.by(() => {
		if (!recipeFg || !predictions.predicted_fg) return null;

		const deviation = predictions.predicted_fg - recipeFg;
		const deviationPoints = Math.round(deviation * 1000);

		// Warn if predicted FG is more than 5 points above recipe target
		if (deviationPoints > 5) {
			return {
				predicted: predictions.predicted_fg,
				target: recipeFg,
				points: deviationPoints
			};
		}
		return null;
	});

	// Confidence level indicator
	let confidenceLevel = $derived.by(() => {
		const conf = predictions.confidence;
		if (conf === undefined || conf === null) return null;
		if (conf >= 0.7) return { label: 'High', color: 'var(--positive)' };
		if (conf >= 0.4) return { label: 'Medium', color: 'var(--status-warn)' };
		return { label: 'Low', color: 'var(--ink-muted)' };
	});

	// Determine fermentation activity status based on sg_rate
	let activityStatus = $derived.by(() => {
		const sgRate = liveReading?.sg_rate;
		if (sgRate === null || sgRate === undefined) return null;

		// sg_rate is in points per hour (e.g., -0.001 means dropping 0.001 SG per hour)
		const absRate = Math.abs(sgRate);

		if (absRate > 0.002) return { label: 'Very Active', color: 'var(--activity-very-active)' };
		if (absRate > 0.0005) return { label: 'Active', color: 'var(--activity-active)' };
		if (absRate > 0.0001) return { label: 'Slowing', color: 'var(--activity-slowing)' };
		return { label: 'Complete', color: 'var(--activity-complete)' };
	});

	// Check for anomalies
	let hasAnomaly = $derived(liveReading?.is_anomaly ?? false);
	let anomalyReasons = $derived(liveReading?.anomaly_reasons ?? []);
</script>

{#if loading}
	<div class="ml-panel loading">
		<p>Loading {isCompleted ? 'summary' : 'predictions'}...</p>
	</div>
{:else if error}
	<div class="ml-panel error">
		<p class="error-text">{error}</p>
	</div>
{:else if predictions.available}
	<div class="ml-panel" class:has-anomaly={hasAnomaly} class:completed={isCompleted}>
		<div class="panel-header">
			<h3 class="panel-title">{isCompleted ? 'Fermentation Summary' : 'Fermentation Intelligence'}</h3>
			{#if !isCompleted}
				<div class="header-controls">
					<select
						class="model-select"
						bind:value={selectedModel}
						onchange={handleModelChange}
						disabled={loading || reloading}
						title="Select prediction model"
					>
						{#each models as m}
							<option value={m.value}>{m.label}</option>
						{/each}
					</select>
					<button
						type="button"
						class="reload-btn"
						onclick={handleReload}
						disabled={reloading || loading}
						title="Recalculate predictions from database history"
					>
						{reloading ? 'Reloading...' : 'Reload'}
					</button>
				</div>
			{/if}
		</div>

		{#if isCompleted}
			<!-- COMPLETED BATCH: Post-Mortem Summary -->
			<div class="summary-section">
				<!-- Prediction Accuracy -->
				{#if predictionAccuracy && actualFg}
					<div class="accuracy-banner" class:accurate={predictionAccuracy.isAccurate} class:close={predictionAccuracy.isClose && !predictionAccuracy.isAccurate}>
						<div class="accuracy-header">
							{#if predictionAccuracy.isAccurate}
								<span class="accuracy-title">Excellent Prediction</span>
							{:else if predictionAccuracy.isClose}
								<span class="accuracy-title">Close Prediction</span>
							{:else}
								<span class="accuracy-title">Prediction Variance</span>
							{/if}
						</div>
						<p class="accuracy-detail">
							Model predicted {formatGravity(predictions.predicted_fg ?? 0)}, actual was {formatGravity(actualFg)}
							<span class="accuracy-diff">({predictionAccuracy.points} points {predictions.predicted_fg && predictions.predicted_fg > actualFg ? 'high' : 'low'})</span>
						</p>
					</div>
				{/if}

				<!-- Final Results Comparison -->
				<div class="comparison-grid">
					<div class="comparison-item">
						<span class="comparison-label">Final Gravity</span>
						<div class="comparison-values">
							<span class="comparison-actual">{formatGravity(actualFg ?? 0)}</span>
							{#if predictions.predicted_fg}
								<span class="comparison-predicted">ML: {formatGravity(predictions.predicted_fg)}</span>
							{/if}
						</div>
					</div>
				</div>

				<!-- Model Info for completed batch -->
				<div class="model-info summary-model">
					{#if predictions.model_type}
						<div class="model-metric">
							<span class="model-label">Model:</span>
							<span class="model-value model-type">{predictions.model_type}</span>
						</div>
					{/if}
					{#if predictions.r_squared !== undefined}
						<div class="model-metric">
							<span class="model-label">Fit:</span>
							<span class="model-value">{(predictions.r_squared * 100).toFixed(0)}%</span>
						</div>
					{/if}
					{#if predictions.num_readings}
						<div class="model-metric">
							<span class="model-label">Points:</span>
							<span class="model-value">{predictions.num_readings}</span>
						</div>
					{/if}
				</div>
			</div>

		{:else}
			<!-- ACTIVE BATCH: Live Predictions -->

			<!-- Anomaly Warning -->
			{#if hasAnomaly}
				<div class="anomaly-banner">
					<div class="anomaly-content">
						<span class="anomaly-label">Anomaly Detected</span>
						{#if anomalyReasons.length > 0}
							<span class="anomaly-reasons">{anomalyReasons.join(', ')}</span>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Stuck Fermentation Warning -->
			{#if stuckFermentationWarning}
				<div class="stuck-warning">
					<div class="stuck-content">
						<span class="stuck-label">Potential Early Stall</span>
						<span class="stuck-detail">
							Model predicts {formatGravity(stuckFermentationWarning.predicted)} vs target {formatGravity(stuckFermentationWarning.target)}
							({stuckFermentationWarning.points} pts high)
						</span>
					</div>
				</div>
			{/if}

			{#if activityStatus}
				<div class="activity-row">
					<span class="progress-label">Activity</span>
					<span class="activity-badge" style="color: {activityStatus.color}">{activityStatus.label}</span>
				</div>
			{/if}

			<div class="metrics">
				<!-- Predicted FG -->
				{#if predictions.predicted_fg}
					<div class="metric">
						<span class="label">Predicted FG:</span>
						<span class="value">{formatGravity(predictions.predicted_fg)}</span>
					</div>
				{/if}

				<!-- Estimated Completion -->
				{#if predictions.estimated_completion}
					{@const days = daysRemaining(predictions.estimated_completion)}
					<div class="metric completion-metric">
						<span class="label">Est. Completion:</span>
						<span class="value">
							{#if days !== null && days <= 0}
								<span class="complete-now">Ready now!</span>
							{:else}
								{formatDate(predictions.estimated_completion)}
								{#if days !== null}
									<span class="days">({days}&thinsp;{days === 1 ? 'day' : 'days'})</span>
								{/if}
							{/if}
						</span>
					</div>
				{/if}

				<!-- Model confidence section -->
				<div class="model-info">
					{#if predictions.model_type}
						<div class="model-metric">
							<span class="model-label">Model:</span>
							<span class="model-value model-type">{predictions.model_type}</span>
						</div>
					{/if}
					{#if confidenceLevel}
						<div class="model-metric">
							<span class="model-label">Conf:</span>
							<span class="model-value" style="color: {confidenceLevel.color}">{confidenceLevel.label}</span>
						</div>
					{/if}
					{#if predictions.num_readings}
						<div class="model-metric">
							<span class="model-label">Points:</span>
							<span class="model-value">{predictions.num_readings}</span>
						</div>
					{/if}
				</div>
			</div>
		{/if}
	</div>
{:else}
	<div class="ml-panel disabled">
		<div class="disabled-header">
			<p class="unavailable-text">{isCompleted ? 'Fermentation summary unavailable' : 'ML predictions unavailable'}</p>
			<button
				type="button"
				class="reload-btn"
				onclick={handleReload}
				disabled={reloading || loading}
				title="Reload predictions from database"
			>
				{reloading ? 'Reloading...' : 'Reload'}
			</button>
		</div>
		<p class="unavailable-hint">
			{#if predictions.reason === 'insufficient_fermentation_progress'}
				Waiting for fermentation to progress (need visible SG drop)
			{:else if predictions.reason === 'insufficient_curve_data'}
				Need more fermentation curve data for reliable prediction
			{:else if predictions.reason === 'insufficient_data'}
				Need at least 10 readings to make predictions
			{:else}
				{isCompleted ? 'No fermentation data recorded' : 'Predictions will appear once fermentation is underway'}
			{/if}
		</p>
	</div>
{/if}

<style>
	.ml-panel {
		border-top: 1px solid var(--rule-strong);
		padding-top: var(--space-sm);
		min-width: 0;
	}
	.ml-panel.has-anomaly {
		border-top-color: color-mix(in oklch, var(--status-warn) 60%, transparent);
	}
	.ml-panel.loading p,
	.unavailable-text,
	.unavailable-hint {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.unavailable-hint {
		margin-top: var(--space-2xs);
		color: var(--ink-muted);
	}
	.error-text {
		font-size: var(--text-sm);
		color: var(--status-danger);
	}
	.disabled-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
	}
	.panel-header {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-sm);
		margin-bottom: var(--space-sm);
	}
	.panel-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0;
	}
	.header-controls {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.model-select,
	.reload-btn {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-primary);
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		border-radius: 4px;
		cursor: pointer;
	}
	.model-select {
		max-width: 11rem;
	}
	.reload-btn:hover:not(:disabled) {
		background: var(--bg-subtle);
	}
	.model-select:disabled,
	.reload-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	/* Completed summary */
	.summary-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-sm);
	}
	.accuracy-banner {
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid var(--rule-strong);
	}
	.accuracy-banner.accurate {
		border-color: color-mix(in oklch, var(--status-steady) 55%, transparent);
	}
	.accuracy-banner.close {
		border-color: color-mix(in oklch, var(--status-warn) 55%, transparent);
	}
	.accuracy-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--ink-secondary);
	}
	.accuracy-banner.accurate .accuracy-title {
		color: var(--status-steady);
	}
	.accuracy-banner.close .accuracy-title {
		color: var(--status-warn);
	}
	.accuracy-detail {
		margin-top: var(--space-2xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.accuracy-diff {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.comparison-grid {
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.comparison-item {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-2xs);
	}
	.comparison-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.comparison-values {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
	}
	.comparison-actual {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--ink-primary);
	}
	.comparison-predicted {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	/* Warnings */
	.anomaly-banner,
	.stuck-warning {
		display: flex;
		align-items: baseline;
		gap: var(--space-sm);
		margin-bottom: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid color-mix(in oklch, var(--status-warn) 50%, transparent);
		background: var(--warning-muted);
	}
	.anomaly-content,
	.stuck-content {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
	}
	.anomaly-label,
	.stuck-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 700;
		text-transform: uppercase;
		letter-spacing: 0.08em;
		color: var(--status-warn);
	}
	.anomaly-reasons,
	.stuck-detail {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	/* Activity */
	.activity-row {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		margin-bottom: var(--space-xs);
	}
	.progress-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.activity-badge {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
	}

	/* Metrics as ledger rows */
	.metrics {
		display: flex;
		flex-direction: column;
		border-top: 1px solid var(--rule-hairline);
	}
	.metric {
		display: flex;
		justify-content: space-between;
		align-items: baseline;
		gap: var(--space-sm);
		padding: var(--space-xs) var(--space-2xs);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.label,
	.model-label {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.value {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums;
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-primary);
		text-align: right;
	}
	.days {
		font-size: var(--text-xs);
		font-weight: 400;
		color: var(--ink-muted);
	}
	.complete-now {
		color: var(--status-steady);
	}
	.model-info {
		display: flex;
		flex-wrap: wrap;
		gap: var(--space-xs) var(--space-md);
		padding-top: var(--space-xs);
	}
	.model-info.summary-model {
		padding-top: 0;
	}
	.model-metric {
		display: flex;
		gap: var(--space-xs);
		align-items: baseline;
	}
	.model-label {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.model-value {
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-secondary);
	}
	.model-value.model-type {
		text-transform: capitalize;
	}
</style>
