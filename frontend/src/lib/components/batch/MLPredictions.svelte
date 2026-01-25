<script lang="ts">
	import { onMount } from 'svelte';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { fetchBatchPredictions, reloadBatchPredictions, type MLPredictions } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';

	interface Props {
		batchId: number;
		batchStatus?: string;
		measuredOg?: number | null;
		measuredFg?: number | null;  // Actual FG from batch
		currentSg?: number | null;
		liveReading?: TiltReading | null;
	}

	let { batchId, batchStatus = 'fermenting', measuredOg = null, measuredFg = null, currentSg = null, liveReading = null }: Props = $props();

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

	// Calculate fermentation progress percentage (OG → FG)
	let fermentationProgress = $derived.by(() => {
		const og = measuredOg ?? predictions.predicted_og;
		const fg = predictions.predicted_fg;
		const current = currentSg ?? liveReading?.sg;

		if (!og || !fg || !current) return null;
		if (og <= fg) return null; // Invalid: OG should be > FG

		const totalDrop = og - fg;
		const currentDrop = og - current;
		const progress = (currentDrop / totalDrop) * 100;

		return Math.min(100, Math.max(0, progress));
	});

	// Calculate apparent attenuation
	let apparentAttenuation = $derived.by(() => {
		const og = measuredOg ?? predictions.predicted_og;
		const current = currentSg ?? liveReading?.sg;

		if (!og || !current || og <= 1.0) return null;

		// Apparent attenuation = (OG - Current) / (OG - 1.0) * 100
		const attenuation = ((og - current) / (og - 1.0)) * 100;
		return Math.min(100, Math.max(0, attenuation));
	});

	// Determine fermentation activity status based on sg_rate
	let activityStatus = $derived.by(() => {
		const sgRate = liveReading?.sg_rate;
		if (sgRate === null || sgRate === undefined) return null;

		// sg_rate is in points per hour (e.g., -0.001 means dropping 0.001 SG per hour)
		const absRate = Math.abs(sgRate);

		if (absRate > 0.002) return { label: 'Very Active', color: 'var(--activity-very-active)', emoji: '🔥' };
		if (absRate > 0.0005) return { label: 'Active', color: 'var(--activity-active)', emoji: '✨' };
		if (absRate > 0.0001) return { label: 'Slowing', color: 'var(--activity-slowing)', emoji: '🐢' };
		return { label: 'Complete', color: 'var(--activity-complete)', emoji: '✓' };
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
		<p class="error-text">⚠️ {error}</p>
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
						{reloading ? 'Reloading...' : '↻'}
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
								<span class="accuracy-icon">✓</span>
								<span class="accuracy-title">Excellent Prediction</span>
							{:else if predictionAccuracy.isClose}
								<span class="accuracy-icon">≈</span>
								<span class="accuracy-title">Close Prediction</span>
							{:else}
								<span class="accuracy-icon">△</span>
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
					<span class="anomaly-icon">⚠️</span>
					<div class="anomaly-content">
						<span class="anomaly-label">Anomaly Detected</span>
						{#if anomalyReasons.length > 0}
							<span class="anomaly-reasons">{anomalyReasons.join(', ')}</span>
						{/if}
					</div>
				</div>
			{/if}

			<!-- Fermentation Progress Section -->
			{#if fermentationProgress !== null}
				<div class="progress-section">
					<div class="progress-header">
						<span class="progress-label">Fermentation Progress</span>
						{#if activityStatus}
							<span class="activity-badge" style="color: {activityStatus.color}">
								{activityStatus.emoji} {activityStatus.label}
							</span>
						{/if}
					</div>
					<div class="fermentation-progress-bar">
						<div class="fermentation-fill" style="width: {fermentationProgress}%"></div>
					</div>
					<div class="progress-labels">
						<span class="og-label">OG: {formatGravity(measuredOg ?? predictions.predicted_og ?? 0)}</span>
						<span class="progress-percent">{fermentationProgress.toFixed(0)}%</span>
						<span class="fg-label">FG: {formatGravity(predictions.predicted_fg ?? 0)}</span>
					</div>
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

				<!-- Attenuation -->
				{#if apparentAttenuation !== null}
					<div class="metric">
						<span class="label">Attenuation:</span>
						<span class="value attenuation">{apparentAttenuation.toFixed(1)}%</span>
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
									<span class="days">({days} {days === 1 ? 'day' : 'days'})</span>
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
				{reloading ? 'Reloading...' : '↻ Reload'}
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
		background: var(--bg-surface);
		border: 1px solid var(--border-default);
		border-radius: 0.5rem;
		padding: 1rem;
		margin-bottom: 1rem;
	}

	.ml-panel.completed {
		border-color: var(--positive);
		background: linear-gradient(135deg, var(--bg-surface) 0%, var(--positive-muted) 100%);
	}

	.ml-panel.has-anomaly {
		border-color: var(--recipe-accent);
		background: linear-gradient(135deg, var(--bg-surface) 0%, var(--recipe-accent-muted) 100%);
	}

	.ml-panel.loading,
	.ml-panel.error {
		text-align: center;
		padding: 2rem;
	}

	.ml-panel.disabled {
		padding: 1rem;
	}

	.disabled-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.disabled-header .unavailable-text {
		margin: 0;
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

	.header-controls {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.model-select {
		padding: 0.25rem 0.5rem;
		font-size: 0.6875rem;
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--border-default);
		border-radius: 0.25rem;
		cursor: pointer;
		transition: all 0.2s ease;
		max-width: 120px;
	}

	.model-select:hover:not(:disabled) {
		color: var(--text-primary);
		border-color: var(--border-hover);
	}

	.model-select:disabled {
		opacity: 0.5;
		cursor: not-allowed;
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

	/* Summary Section (Completed Batches) */
	.summary-section {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.accuracy-banner {
		padding: 0.75rem;
		border-radius: 0.375rem;
		background: rgba(251, 191, 36, 0.1);
		border: 1px solid rgba(251, 191, 36, 0.3);
	}

	.accuracy-banner.accurate {
		background: rgba(34, 197, 94, 0.1);
		border-color: rgba(34, 197, 94, 0.3);
	}

	.accuracy-banner.close {
		background: rgba(59, 130, 246, 0.1);
		border-color: rgba(59, 130, 246, 0.3);
	}

	.accuracy-header {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		margin-bottom: 0.375rem;
	}

	.accuracy-icon {
		font-size: 1rem;
	}

	.accuracy-banner.accurate .accuracy-icon {
		color: var(--positive);
	}

	.accuracy-banner.close .accuracy-icon {
		color: var(--tilt-blue);
	}

	.accuracy-title {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.accuracy-detail {
		font-size: 0.75rem;
		color: var(--text-secondary);
		margin: 0;
	}

	.accuracy-diff {
		color: var(--text-muted);
	}

	.comparison-grid {
		display: flex;
		flex-direction: column;
		gap: 0.5rem;
	}

	.comparison-item {
		display: flex;
		justify-content: space-between;
		align-items: center;
		padding: 0.5rem 0.75rem;
		background: var(--bg-elevated);
		border-radius: 0.375rem;
	}

	.comparison-label {
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	.comparison-values {
		display: flex;
		align-items: center;
		gap: 0.75rem;
	}

	.comparison-actual {
		font-family: var(--font-mono);
		font-size: 0.9375rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.comparison-predicted {
		font-family: var(--font-mono);
		font-size: 0.6875rem;
		color: var(--text-muted);
		padding: 0.125rem 0.375rem;
		background: var(--bg-surface);
		border-radius: 0.25rem;
	}

	.summary-model {
		margin-top: 0.5rem;
		padding-top: 0.5rem;
		border-top: 1px solid var(--border-default);
	}

	/* Anomaly Banner */
	.anomaly-banner {
		display: flex;
		align-items: center;
		gap: 0.75rem;
		padding: 0.75rem;
		margin-bottom: 1rem;
		background: rgba(245, 158, 11, 0.1);
		border: 1px solid rgba(245, 158, 11, 0.3);
		border-radius: 0.375rem;
	}

	.anomaly-icon {
		font-size: 1.25rem;
	}

	.anomaly-content {
		display: flex;
		flex-direction: column;
		gap: 0.125rem;
	}

	.anomaly-label {
		font-size: 0.8125rem;
		font-weight: 600;
		color: var(--recipe-accent-hover);
	}

	.anomaly-reasons {
		font-size: 0.75rem;
		color: var(--text-secondary);
	}

	/* Fermentation Progress Section */
	.progress-section {
		margin-bottom: 1rem;
		padding-bottom: 1rem;
		border-bottom: 1px solid var(--border-default);
	}

	.progress-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.5rem;
	}

	.progress-label {
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		text-transform: uppercase;
		letter-spacing: 0.025em;
	}

	.activity-badge {
		font-size: 0.75rem;
		font-weight: 600;
		display: flex;
		align-items: center;
		gap: 0.25rem;
	}

	.fermentation-progress-bar {
		height: 12px;
		background: var(--bg-elevated);
		border-radius: 6px;
		overflow: hidden;
		margin-bottom: 0.5rem;
	}

	.fermentation-fill {
		height: 100%;
		background: linear-gradient(90deg, var(--accent) 0%, var(--positive) 100%);
		border-radius: 6px;
		transition: width 0.5s ease;
	}

	.progress-labels {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.og-label,
	.fg-label {
		font-size: 0.6875rem;
		color: var(--text-muted);
		font-family: var(--font-mono);
	}

	.progress-percent {
		font-size: 0.875rem;
		font-weight: 700;
		color: var(--text-primary);
		font-family: var(--font-mono);
	}

	/* Metrics */
	.metrics {
		display: flex;
		flex-direction: column;
		gap: 0.625rem;
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
	}

	.value {
		font-size: 0.8125rem;
		color: var(--text-primary);
		font-family: var(--font-mono);
		font-weight: 500;
	}

	.attenuation {
		color: var(--tilt-purple);
	}

	.days {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.complete-now {
		color: var(--positive);
		font-weight: 600;
	}

	/* Model Info */
	.model-info {
		display: flex;
		gap: 1rem;
		margin-top: 0.75rem;
		padding-top: 0.75rem;
		border-top: 1px solid var(--border-default);
	}

	.model-metric {
		display: flex;
		align-items: center;
		gap: 0.375rem;
	}

	.model-label {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	.model-value {
		font-size: 0.6875rem;
		font-family: var(--font-mono);
		color: var(--text-secondary);
	}

	.model-value.model-type {
		text-transform: capitalize;
		color: var(--accent);
	}

	/* Unavailable state */
	.unavailable-text {
		color: var(--text-muted);
		font-size: 0.875rem;
		margin-bottom: 0.25rem;
	}

	.unavailable-hint {
		color: var(--text-muted);
		font-size: 0.75rem;
		opacity: 0.7;
	}

	.error-text {
		color: var(--negative);
		font-size: 0.8125rem;
	}
</style>
