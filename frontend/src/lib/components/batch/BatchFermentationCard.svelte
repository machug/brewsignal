<script lang="ts">
	import type { BatchResponse, BatchProgressResponse } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatGravity, formatTemp, getTempUnit } from '$lib/stores/config.svelte';
	import { timeSince, getSignalStrength } from '$lib/utils/signal';
	import BatchCard from './BatchCard.svelte';

	interface Props {
		batch: BatchResponse;
		currentSg?: number | null;
		progress?: BatchProgressResponse | null;
		liveReading?: TiltReading | null;
	}

	let { batch, currentSg, progress, liveReading }: Props = $props();

	// Device info (merged from BatchDeviceCard)
	let isBleDevice = $derived(liveReading?.device_type === 'tilt');
	let signal = $derived(isBleDevice && liveReading?.rssi ? getSignalStrength(liveReading.rssi) : null);
	let deviceDisplayName = $derived.by(() => {
		if (!liveReading) return batch.device_id || null;
		const deviceType = liveReading.device_type;
		if (deviceType === 'tilt') return `${liveReading.color} Tilt`;
		if (deviceType === 'gravitymon') return `GravityMon`;
		if (deviceType === 'ispindel') return `iSpindel`;
		if (deviceType === 'floaty') return `Floaty`;
		return liveReading.color || liveReading.id;
	});

	// Get the best available current gravity
	let sg = $derived(currentSg ?? progress?.measured?.current_sg);
	let temp = $derived(liveReading?.temp ?? progress?.temperature?.current);
	let lastSeen = $derived(liveReading?.last_seen);
	let lastSeenText = $derived(lastSeen ? timeSince(lastSeen) : null);
	let tempUnit = $derived(getTempUnit());

	// Calculate metrics
	let metrics = $derived.by(() => {
		if (!batch.measured_og || !sg) return null;

		// ABV: (OG - Current SG) × 131.25
		const abv = Math.max(0, (batch.measured_og - sg) * 131.25);

		// Attenuation: ((OG - Current SG) / (OG - 1.000)) × 100
		const denominator = batch.measured_og - 1.0;
		const attenuation = denominator !== 0
			? Math.max(0, Math.min(100, ((batch.measured_og - sg) / denominator) * 100))
			: 0;

		return { abv, attenuation };
	});

	// Calculate progress position (0-100%)
	// OG is LEFT (high), Target FG is RIGHT (low)
	// Progress = how far current has dropped from OG toward FG
	let progressPercent = $derived.by(() => {
		const og = batch.measured_og;
		const fg = batch.recipe?.fg;
		if (!og || !fg || !sg) return null;

		const totalDrop = og - fg;  // e.g., 1.047 - 1.012 = 0.035
		const currentDrop = og - sg; // e.g., 1.047 - 1.048 = -0.001 (at start)

		if (totalDrop <= 0) return null;

		// Clamp to 0-100%
		return Math.max(0, Math.min(100, (currentDrop / totalDrop) * 100));
	});

	// Determine fermentation status
	let isFermenting = $derived(batch.status === 'fermenting' || batch.status === 'conditioning');

	function formatSG(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatGravity(value);
	}

	function formatPercent(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return `${value.toFixed(1)}%`;
	}

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}
</script>

<BatchCard title="Fermentation">
	{#if sg && isFermenting}
		<!-- Live indicator with device info -->
		<div class="status-row">
			<div class="status-left">
				<div class="live-indicator">
					<span class="pulse-dot"></span>
					<span class="status-text">LIVE</span>
				</div>
				{#if deviceDisplayName}
					<div class="device-badge">
						<span class="device-name">{deviceDisplayName}</span>
						{#if signal}
							<div class="signal-bars">
								{#each Array(4) as _, i}
									<div
										class="signal-bar"
										style="height: {4 + i * 2}px; background: {i < signal.bars ? signal.color : 'var(--bg-hover)'};"
									></div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
			</div>
			{#if lastSeenText}
				<span class="updated-text">{lastSeenText}</span>
			{/if}
		</div>

		<!-- Hero: Current Gravity + Temperature -->
		<div class="hero-section">
			<div class="hero-metric gravity">
				<span class="hero-value">{formatSG(sg)}</span>
				<span class="hero-label">Gravity</span>
			</div>
			{#if temp != null}
				<div class="hero-divider"></div>
				<div class="hero-metric temperature">
					<span class="hero-value">{formatTempValue(temp)}<span class="hero-unit">{tempUnit}</span></span>
					<span class="hero-label">Temperature</span>
				</div>
			{/if}
		</div>

		<!-- Gravity Drop Progress Bar -->
		{#if progressPercent !== null && batch.measured_og && batch.recipe?.fg}
			<div class="progress-section">
				<div class="progress-labels">
					<div class="progress-endpoint start">
						<span class="endpoint-value">{formatSG(batch.measured_og)}</span>
						<span class="endpoint-label">OG</span>
					</div>
					<div class="progress-current">
						<span class="current-percent">{progressPercent.toFixed(0)}%</span>
					</div>
					<div class="progress-endpoint end">
						<span class="endpoint-value">{formatSG(batch.recipe.fg)}</span>
						<span class="endpoint-label">Target FG</span>
					</div>
				</div>

				<div class="progress-track">
					<div class="progress-fill" style="width: {progressPercent}%"></div>
					<div
						class="progress-marker"
						style="left: {progressPercent}%"
						class:at-start={progressPercent < 3}
					>
						<div class="marker-dot"></div>
						<div class="marker-value">{formatSG(sg)}</div>
					</div>
				</div>

				{#if progress?.progress?.sg_remaining != null && progress.progress.sg_remaining > 0}
					<div class="remaining-text">
						{progress.progress.sg_remaining.toFixed(3)} points to go
					</div>
				{/if}
			</div>
		{/if}

		<!-- Compact Metrics Row -->
		{#if metrics}
			<div class="metrics-row">
				<div class="metric">
					<span class="metric-value">{formatPercent(metrics.abv)}</span>
					<span class="metric-label">ABV</span>
				</div>
				<div class="metric">
					<span class="metric-value">{formatPercent(metrics.attenuation)}</span>
					<span class="metric-label">Attenuation</span>
				</div>
			</div>
		{/if}

	{:else if batch.measured_og}
		<!-- Completed or no live readings -->
		<!-- Use batch values if available, otherwise fall back to progress data -->
		{@const finalGravity = batch.measured_fg ?? progress?.measured?.current_sg}
		{@const abv = batch.measured_abv ?? progress?.measured?.abv}
		{@const attenuation = batch.measured_attenuation ?? progress?.measured?.attenuation}
		<div class="completed-grid">
			<div class="completed-metric">
				<span class="completed-value">{formatSG(batch.measured_og)}</span>
				<span class="completed-label">Original Gravity</span>
			</div>
			<div class="completed-metric">
				<span class="completed-value">{formatSG(finalGravity)}</span>
				<span class="completed-label">Final Gravity</span>
			</div>
			<div class="completed-metric">
				<span class="completed-value">{abv != null ? formatPercent(abv) : '--'}</span>
				<span class="completed-label">ABV</span>
			</div>
			<div class="completed-metric">
				<span class="completed-value">{attenuation != null ? formatPercent(attenuation) : '--'}</span>
				<span class="completed-label">Attenuation</span>
			</div>
		</div>

	{:else}
		<!-- No OG set -->
		<div class="empty-state">
			<div class="empty-icon">◎</div>
			<p class="empty-text">Set Original Gravity to track fermentation</p>
		</div>
	{/if}
</BatchCard>

<style>
	/* Status Row */
	.status-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 0.5rem;
		margin-bottom: 1rem;
	}

	.status-left {
		display: flex;
		align-items: center;
		gap: 0.5rem;
	}

	.live-indicator {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.625rem;
		background: rgba(245, 158, 11, 0.12);
		border-radius: 9999px;
		font-size: 0.625rem;
		font-weight: 700;
		color: var(--recipe-accent);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.pulse-dot {
		width: 6px;
		height: 6px;
		background: var(--recipe-accent);
		border-radius: 50%;
		animation: pulse 2s ease-in-out infinite;
	}

	@keyframes pulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.5; transform: scale(1.2); }
	}

	.device-badge {
		display: inline-flex;
		align-items: center;
		gap: 0.375rem;
		padding: 0.25rem 0.5rem;
		background: var(--bg-elevated);
		border-radius: 9999px;
		font-size: 0.6875rem;
	}

	.device-name {
		color: var(--positive);
		font-weight: 500;
	}

	.signal-bars {
		display: flex;
		align-items: flex-end;
		gap: 1px;
	}

	.signal-bar {
		width: 2px;
		border-radius: 1px;
	}

	.updated-text {
		font-size: 0.6875rem;
		color: var(--text-muted);
	}

	/* Hero Section */
	.hero-section {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 2rem;
		padding: 1.5rem 1rem;
		margin-bottom: 1.5rem;
		background: linear-gradient(135deg, rgba(245, 158, 11, 0.06) 0%, rgba(217, 119, 6, 0.03) 100%);
		border-radius: 0.75rem;
		border: 1px solid rgba(245, 158, 11, 0.15);
	}

	.hero-metric {
		text-align: center;
	}

	.hero-value {
		display: block;
		font-family: 'JetBrains Mono', 'SF Mono', monospace;
		font-size: 2.75rem;
		font-weight: 500;
		color: var(--text-primary);
		line-height: 1;
		letter-spacing: -0.02em;
	}

	.hero-metric.temperature .hero-value {
		font-size: 2rem;
		color: var(--temp-ambient);
	}

	.hero-unit {
		font-size: 1rem;
		color: var(--text-secondary);
		margin-left: 0.125rem;
	}

	.hero-label {
		display: block;
		margin-top: 0.5rem;
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
	}

	.hero-divider {
		width: 1px;
		height: 3rem;
		background: var(--border-subtle);
	}

	/* Progress Section */
	.progress-section {
		margin-bottom: 1.5rem;
	}

	.progress-labels {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		margin-bottom: 0.5rem;
	}

	.progress-endpoint {
		text-align: center;
	}

	.progress-endpoint.start {
		text-align: left;
	}

	.progress-endpoint.end {
		text-align: right;
	}

	.endpoint-value {
		display: block;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.875rem;
		font-weight: 600;
		color: var(--text-secondary);
	}

	.endpoint-label {
		font-size: 0.5625rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	.progress-current {
		flex: 1;
		text-align: center;
	}

	.current-percent {
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.25rem;
		font-weight: 700;
		color: var(--recipe-accent);
	}

	.progress-track {
		position: relative;
		height: 8px;
		background: var(--bg-elevated);
		border-radius: 4px;
		overflow: visible;
	}

	.progress-fill {
		position: absolute;
		top: 0;
		left: 0;
		height: 100%;
		background: linear-gradient(90deg, var(--activity-active), var(--recipe-accent));
		border-radius: 4px;
		transition: width 0.6s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.progress-marker {
		position: absolute;
		top: 50%;
		transform: translate(-50%, -50%);
		display: flex;
		flex-direction: column;
		align-items: center;
		transition: left 0.6s cubic-bezier(0.4, 0, 0.2, 1);
	}

	.progress-marker.at-start {
		transform: translate(0, -50%);
	}

	.progress-marker.at-start .marker-value {
		left: 0;
		transform: translateX(0);
	}

	.marker-dot {
		width: 16px;
		height: 16px;
		background: var(--recipe-accent-muted);
		border: 3px solid var(--recipe-accent);
		border-radius: 50%;
		box-shadow: 0 0 0 3px var(--bg-surface), 0 2px 8px var(--recipe-accent-border);
		animation: markerPulse 2.5s ease-in-out infinite;
	}

	@keyframes markerPulse {
		0%, 100% { box-shadow: 0 0 0 3px var(--bg-surface), 0 2px 8px var(--recipe-accent-border); }
		50% { box-shadow: 0 0 0 3px var(--bg-surface), 0 2px 16px var(--recipe-accent-border); }
	}

	.marker-value {
		position: absolute;
		top: calc(100% + 0.5rem);
		left: 50%;
		transform: translateX(-50%);
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--recipe-accent);
		white-space: nowrap;
		background: var(--bg-surface);
		padding: 0.125rem 0.375rem;
		border-radius: 0.25rem;
	}

	.remaining-text {
		margin-top: 1.25rem;
		text-align: center;
		font-family: 'JetBrains Mono', monospace;
		font-size: 0.75rem;
		color: var(--text-muted);
	}

	/* Metrics Row */
	.metrics-row {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.75rem;
	}

	.metric {
		text-align: center;
		padding: 0.875rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
		border: 1px solid transparent;
		transition: all 0.2s ease;
	}

	.metric:hover {
		border-color: var(--border-subtle);
	}

	.metric-value {
		display: block;
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.25rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.metric-label {
		display: block;
		margin-top: 0.25rem;
		font-size: 0.5625rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Completed Grid */
	.completed-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: 0.75rem;
	}

	.completed-metric {
		text-align: center;
		padding: 1rem;
		background: var(--bg-elevated);
		border-radius: 0.5rem;
	}

	.completed-value {
		display: block;
		font-family: 'JetBrains Mono', monospace;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
	}

	.completed-label {
		display: block;
		margin-top: 0.375rem;
		font-size: 0.625rem;
		font-weight: 600;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.05em;
	}

	/* Empty State */
	.empty-state {
		text-align: center;
		padding: 2.5rem 1rem;
	}

	.empty-icon {
		font-size: 2.5rem;
		color: var(--text-muted);
		opacity: 0.3;
		margin-bottom: 0.75rem;
	}

	.empty-text {
		font-size: 0.875rem;
		color: var(--text-muted);
		margin: 0;
	}

	/* Responsive */
	@media (max-width: 480px) {
		.hero-section {
			flex-direction: column;
			gap: 1rem;
		}

		.hero-divider {
			width: 3rem;
			height: 1px;
		}

		.hero-value {
			font-size: 2.25rem;
		}

		.hero-metric.temperature .hero-value {
			font-size: 1.75rem;
		}
	}
</style>
