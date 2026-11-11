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
					<span class="pulse-dot" aria-hidden="true"></span>
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
										style="height: {4 + i * 2}px; background: {i < signal.bars ? signal.color : 'var(--rule-strong)'};"
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

		<!-- Readout grid: gravity, temperature, ABV, attenuation -->
		<div class="matrix">
			<div class="cell">
				<span class="label">Gravity</span>
				<span class="primary num">{formatSG(sg)}</span>
			</div>
			<div class="cell">
				<span class="label">Temperature</span>
				<span class="primary num">{#if temp != null}{formatTempValue(temp)}<span class="unit">&thinsp;{tempUnit}</span>{:else}--{/if}</span>
			</div>
			<div class="cell">
				<span class="label">ABV</span>
				<span class="primary num">{metrics ? metrics.abv.toFixed(1) : '--'}<span class="unit">%</span></span>
			</div>
			<div class="cell">
				<span class="label">Attenuation</span>
				<span class="primary num">{metrics ? metrics.attenuation.toFixed(0) : '--'}<span class="unit">%</span></span>
			</div>
		</div>

		<!-- Gravity Drop Progress Bar -->
		{#if progressPercent !== null && batch.measured_og && batch.recipe?.fg}
			<div class="progress-section">
				<div class="progress-labels">
					<div class="progress-endpoint start">
						<span class="endpoint-value num">{formatSG(batch.measured_og)}</span>
						<span class="endpoint-label">OG</span>
					</div>
					<div class="progress-current">
						<span class="current-percent num">{progressPercent.toFixed(0)}%</span>
					</div>
					<div class="progress-endpoint end">
						<span class="endpoint-value num">{formatSG(batch.recipe.fg)}</span>
						<span class="endpoint-label">Target FG</span>
					</div>
				</div>

				<div class="progress-track" role="progressbar" aria-valuenow={Math.round(progressPercent)} aria-valuemin="0" aria-valuemax="100" aria-label="Gravity drop progress">
					<div class="progress-fill" style="width: {progressPercent}%"></div>
				</div>

				{#if progress?.progress?.sg_remaining != null && progress.progress.sg_remaining > 0}
					<div class="remaining-text num">
						{progress.progress.sg_remaining.toFixed(3)} points to go
					</div>
				{/if}
			</div>
		{/if}

	{:else if batch.measured_og}
		<!-- Completed or no live readings -->
		<!-- Use batch values if available, otherwise fall back to progress data -->
		{@const finalGravity = batch.measured_fg ?? progress?.measured?.current_sg}
		{@const abv = batch.measured_abv ?? progress?.measured?.abv}
		{@const attenuation = batch.measured_attenuation ?? progress?.measured?.attenuation}
		<div class="matrix">
			<div class="cell">
				<span class="primary num">{formatSG(batch.measured_og)}</span>
				<span class="label">OG</span>
			</div>
			<div class="cell">
				<span class="primary num">{formatSG(finalGravity)}</span>
				<span class="label">FG</span>
			</div>
			<div class="cell">
				<span class="primary num">{abv != null ? abv.toFixed(1) : '--'}<span class="unit">%</span></span>
				<span class="label">ABV</span>
			</div>
			<div class="cell">
				<span class="primary num">{attenuation != null ? attenuation.toFixed(0) : '--'}<span class="unit">%</span></span>
				<span class="label">Attenuation</span>
			</div>
		</div>

	{:else}
		<!-- No OG set -->
		<div class="empty-state">
						<p class="empty-text">Set Original Gravity to track fermentation</p>
		</div>
	{/if}
</BatchCard>

<style>
	.num {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
		letter-spacing: -0.02em;
	}
	.unit {
		font-family: var(--font-body);
		font-size: 0.78em;
		font-weight: 400;
		color: var(--ink-muted);
		letter-spacing: 0;
	}

	/* Status row */
	.status-row {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: var(--space-xs);
		margin-bottom: var(--space-sm);
	}
	.status-left {
		display: flex;
		align-items: center;
		flex-wrap: wrap;
		gap: var(--space-xs);
	}
	.live-indicator {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 7px;
		border: 1px solid var(--accent-rule);
		border-radius: 2px;
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		color: var(--accent);
		text-transform: uppercase;
		letter-spacing: 0.06em;
	}
	.pulse-dot {
		width: 6px;
		height: 6px;
		background: var(--accent);
		border-radius: 50%;
		animation: pulse 2s ease-in-out infinite;
	}
	@keyframes pulse {
		0%, 100% { opacity: 1; }
		50% { opacity: 0.4; }
	}
	.device-badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		padding: 2px 8px;
		border: 1px solid var(--rule-hairline);
		border-radius: 2px;
		font-family: var(--font-display);
		font-size: var(--text-xs);
	}
	.device-name {
		color: var(--ink-primary);
		font-weight: 600;
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
		font-family: var(--font-num);
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	/* Readout grid */
	.matrix {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		border-top: 1px solid var(--rule-strong);
		border-bottom: 1px solid var(--rule-hairline);
		background: var(--bg-surface);
	}
	.cell {
		display: grid;
		grid-template-rows: 1.25rem auto;
		row-gap: var(--space-2xs);
		padding: var(--space-md);
		border-right: 1px solid var(--rule-hairline);
		min-width: 0;
	}
	.cell:last-child {
		border-right: none;
	}
	.label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
		white-space: nowrap;
	}
	.primary {
		font-size: var(--text-xl);
		font-weight: 600;
		line-height: 1.05;
		color: var(--ink-primary);
	}

	/* Progress */
	.progress-section {
		margin-top: var(--space-md);
	}
	.progress-labels {
		display: flex;
		justify-content: space-between;
		align-items: flex-end;
		margin-bottom: var(--space-xs);
	}
	.progress-endpoint.end {
		text-align: right;
	}
	.endpoint-value {
		display: block;
		font-size: var(--text-sm);
		font-weight: 600;
		color: var(--ink-secondary);
	}
	.endpoint-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.07em;
	}
	.progress-current {
		flex: 1;
		text-align: center;
	}
	.current-percent {
		font-size: var(--text-lg);
		font-weight: 600;
		color: var(--accent);
	}
	.progress-track {
		position: relative;
		height: 4px;
		background: var(--rule-hairline);
	}
	.progress-fill {
		height: 100%;
		background: var(--accent);
		transition: width 600ms var(--ease-out-quart);
	}
	.remaining-text {
		margin-top: var(--space-xs);
		text-align: center;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	/* Empty state */
	.empty-state {
		padding: var(--space-xl) var(--space-md);
		text-align: center;
	}
	.empty-text {
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}

	@media (max-width: 760px) {
		.matrix {
			grid-template-columns: repeat(2, minmax(0, 1fr));
		}
		.cell:nth-child(2) {
			border-right: none;
		}
		.cell:nth-child(-n + 2) {
			border-bottom: 1px solid var(--rule-hairline);
		}
		.cell {
			padding: var(--space-sm);
		}
		.primary {
			font-size: 1.75rem;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.pulse-dot {
			animation: none;
		}
	}
</style>
