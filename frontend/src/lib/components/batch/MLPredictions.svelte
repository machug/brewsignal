<script lang="ts">
	import { onMount } from 'svelte';
	import { formatGravity } from '$lib/stores/config.svelte';
	import { fetchBatchPredictions, reloadBatchPredictions, type MLPredictions } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';

	interface Props {
		batchId: number;
		measuredOg?: number | null;
		currentSg?: number | null;
		liveReading?: TiltReading | null;
	}

	let { batchId, measuredOg = null, currentSg = null, liveReading = null }: Props = $props();

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

		if (absRate > 0.002) return { label: 'Very Active', color: '#22c55e', emoji: '🔥' };
		if (absRate > 0.0005) return { label: 'Active', color: '#84cc16', emoji: '✨' };
		if (absRate > 0.0001) return { label: 'Slowing', color: '#eab308', emoji: '🐢' };
		return { label: 'Complete', color: '#6b7280', emoji: '✓' };
	});

	// Check for anomalies
	let hasAnomaly = $derived(liveReading?.is_anomaly ?? false);
	let anomalyReasons = $derived(liveReading?.anomaly_reasons ?? []);
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
	<div class="ml-panel" class:has-anomaly={hasAnomaly}>
		<div class="panel-header">
			<h3 class="panel-title">Fermentation Intelligence</h3>
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
				{#if predictions.r_squared !== undefined}
					<div class="model-metric">
						<span class="model-label">Model fit:</span>
						<span class="model-value">{(predictions.r_squared * 100).toFixed(0)}%</span>
					</div>
				{/if}
				{#if predictions.num_readings}
					<div class="model-metric">
						<span class="model-label">Data points:</span>
						<span class="model-value">{predictions.num_readings}</span>
					</div>
				{/if}
			</div>
		</div>
	</div>
{:else}
	<div class="ml-panel disabled">
		<div class="disabled-header">
			<p class="unavailable-text">ML predictions unavailable</p>
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
				Predictions will appear once fermentation is underway
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

	.ml-panel.has-anomaly {
		border-color: #f59e0b;
		background: linear-gradient(135deg, var(--bg-surface) 0%, rgba(245, 158, 11, 0.05) 100%);
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
		color: #d97706;
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
		background: linear-gradient(90deg, #3b82f6 0%, #22c55e 100%);
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
		color: #8b5cf6;
	}

	.days {
		color: var(--text-muted);
		font-size: 0.75rem;
	}

	.complete-now {
		color: #22c55e;
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
