<script lang="ts">
	import { configState, formatTemp, getTempUnit, formatGravity, getGravityUnit } from '$lib/stores/config.svelte';
	import { updateBatch, fetchBatchControlEvents, type BatchResponse, type BatchProgressResponse, type ControlEvent } from '$lib/api';
	import FermentationChart from './FermentationChart.svelte';
	import { tiltsState } from '$lib/stores/tilts.svelte';

	interface Props {
		batch: BatchResponse;
		progress?: BatchProgressResponse;
		expanded?: boolean;
		wide?: boolean;
		onToggleExpand?: () => void;
		onBatchUpdated?: () => Promise<void>;
	}

	let { batch, progress, expanded = false, wide = false, onToggleExpand, onBatchUpdated }: Props = $props();

	// Derive device reading from batch.device_id + WebSocket state
	// Direct lookup by device_id (no color-based heuristics)
	let deviceReading = $derived(
		batch.device_id ? tiltsState.tilts.get(batch.device_id) ?? null : null
	);

	// Display values derived from batch/progress/device
	let displayName = $derived(batch.name || batch.recipe?.name || `Batch #${batch.batch_number}`);
	let currentSg = $derived(progress?.measured?.current_sg ?? batch.measured_og ?? 1.000);
	let currentTemp = $derived(progress?.temperature?.current ?? null);
	let deviceColor = $derived(deviceReading?.color ?? 'BLACK');
	let rssi = $derived(deviceReading?.rssi ?? null);
	let batteryPercent = $derived(deviceReading?.battery_percent ?? null);
	let deviceType = $derived(deviceReading?.device_type ?? null);
	// HTTP devices (GravityMon, iSpindel) have battery but no meaningful RSSI
	let isBleDevice = $derived(deviceType === 'tilt' || deviceType === null);
	let isPaired = $derived(deviceReading?.paired ?? true);
	let lastSeen = $derived(deviceReading?.last_seen ?? new Date().toISOString());
	let sgRaw = $derived(deviceReading?.sg_raw ?? currentSg);
	let tempRaw = $derived(deviceReading?.temp_raw ?? currentTemp);
	// ML metrics
	let confidence = $derived(deviceReading?.confidence ?? null);
	let isAnomaly = $derived(deviceReading?.is_anomaly ?? false);
	let anomalyReasons = $derived(deviceReading?.anomaly_reasons ?? []);
	let confidenceBadge = $derived(getConfidenceBadge(confidence));

	// Track if chart has ever been shown (to avoid mounting until first expand)
	let chartMounted = $state(false);
	let controlEvents = $state<ControlEvent[]>([]);
	let controlEventsLoaded = $state(false);

	$effect(() => {
		if (expanded && !chartMounted) {
			chartMounted = true;
			// Fetch control events when chart first mounts
			if (!controlEventsLoaded) {
				fetchBatchControlEvents(batch.id, 168).then(events => {
					controlEvents = events;
					controlEventsLoaded = true;
				}).catch(err => {
					console.error('Failed to fetch control events:', err);
					controlEvents = [];
					controlEventsLoaded = true;
				});
			}
		}
	});

	// Beer name editing state
	let isEditing = $state(false);
	let editValue = $state('');
	let inputRef = $state<HTMLInputElement | null>(null);
	let saving = $state(false);
	let saveError = $state<string | null>(null);

	function startEditing() {
		editValue = displayName;
		isEditing = true;
		saveError = null;
		// Focus input after DOM update
		setTimeout(() => inputRef?.focus(), 0);
	}

	async function saveEdit() {
		if (saving) return;
		const trimmed = editValue.trim();
		if (!trimmed || trimmed === displayName) {
			isEditing = false;
			saveError = null;
			return;
		}
		saving = true;
		saveError = null;
		try {
			await updateBatch(batch.id, { name: trimmed });
			isEditing = false;
			// Trigger parent to refetch batches
			if (onBatchUpdated) {
				await onBatchUpdated();
			}
		} catch (e) {
			console.error('Failed to update batch name:', e);
			saveError = e instanceof Error ? e.message : 'Failed to save batch name';
			// Keep editing mode open on error so user can retry
		} finally {
			saving = false;
		}
	}

	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			saveEdit();
		} else if (e.key === 'Escape') {
			isEditing = false;
		}
	}

	// Reactive units from config
	let tempUnit = $derived(getTempUnit());
	let gravityUnit = $derived(getGravityUnit());

	// CSS variable colors for the tilt accent
	const colorVars: Record<string, string> = {
		RED: 'var(--tilt-red)',
		GREEN: 'var(--tilt-green)',
		BLACK: 'var(--tilt-black)',
		PURPLE: 'var(--tilt-purple)',
		ORANGE: 'var(--tilt-orange)',
		BLUE: 'var(--tilt-blue)',
		YELLOW: 'var(--tilt-yellow)',
		PINK: 'var(--tilt-pink)'
	};

	function formatSG(sg: number): string {
		return formatGravity(sg);
	}

	function formatTempValue(temp: number): string {
		return formatTemp(temp);
	}

	function getSignalStrength(rssi: number): { bars: number; color: string; label: string } {
		if (rssi >= -50) return { bars: 4, color: 'var(--positive)', label: 'Excellent' };
		if (rssi >= -60) return { bars: 3, color: 'var(--positive)', label: 'Good' };
		if (rssi >= -70) return { bars: 2, color: 'var(--warning)', label: 'Fair' };
		return { bars: 1, color: 'var(--negative)', label: 'Weak' };
	}

	function getBatteryLevel(percent: number): { color: string; label: string } {
		if (percent >= 80) return { color: 'var(--positive)', label: 'Good' };
		if (percent >= 40) return { color: 'var(--warning)', label: 'Medium' };
		if (percent >= 20) return { color: 'var(--warning)', label: 'Low' };
		return { color: 'var(--negative)', label: 'Critical' };
	}

	function getConfidenceBadge(conf: number | null): { emoji: string; label: string; color: string } | null {
		if (conf === null || conf === undefined) return null;
		if (conf >= 0.8) return { emoji: '🟢', label: 'High', color: 'var(--positive)' };
		if (conf >= 0.5) return { emoji: '🟡', label: 'Medium', color: 'var(--warning)' };
		return { emoji: '🔴', label: 'Low', color: 'var(--negative)' };
	}

	function timeSince(isoString: string): string {
		const seconds = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
		if (seconds < 10) return 'just now';
		if (seconds < 60) return `${seconds}s ago`;
		const minutes = Math.floor(seconds / 60);
		if (minutes < 60) return `${minutes}m ago`;
		const hours = Math.floor(minutes / 60);
		if (hours < 24) return `${hours}h ago`;
		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	let accentColor = $derived(colorVars[deviceColor] || 'var(--tilt-black)');
	let signal = $derived(rssi !== null ? getSignalStrength(rssi) : { bars: 0, color: 'var(--text-muted)', label: 'No Signal' });
	let battery = $derived(batteryPercent !== null ? getBatteryLevel(batteryPercent) : null);
	let lastSeenText = $derived(timeSince(lastSeen));
</script>

<div
	class="card"
	class:expanded
	class:wide
>
	<!-- Accent bar -->
	<div
		class="h-0.5"
		style="background: {accentColor};"
	></div>

	<div class="p-5">
		<!-- Header row -->
		<div class="flex justify-between items-start mb-5">
			<div class="flex-1 min-w-0 mr-3">
				{#if isEditing}
					<div class="flex flex-col gap-1">
						<input
							type="text"
							bind:this={inputRef}
							bind:value={editValue}
							onblur={saveEdit}
							onkeydown={handleKeydown}
							disabled={saving}
							class="beer-name-input"
							class:error={saveError}
							maxlength="100"
						/>
						{#if saveError}
							<span class="error-message">{saveError}</span>
						{/if}
					</div>
				{:else}
					<button
						type="button"
						class="beer-name-btn"
						onclick={startEditing}
						title="Click to edit batch name"
					>
						<h3 class="text-lg font-semibold text-[var(--text-primary)] tracking-tight truncate">
							{displayName}
						</h3>
						<svg class="edit-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
						</svg>
					</button>
				{/if}
				<div class="flex items-center gap-2 mt-1">
					<span
						class="w-2 h-2 rounded-full"
						style="background: {accentColor};"
					></span>
					<span class="text-sm text-[var(--text-muted)] font-medium">{deviceColor}</span>
				</div>
			</div>

			<div class="flex flex-col items-end gap-2">
				<!-- Signal indicator (BLE) or Battery indicator (HTTP) -->
				{#if isBleDevice && rssi !== null}
					<div class="flex flex-col items-end gap-1" title="{signal.label} signal ({rssi} dBm)">
						<div class="flex items-end gap-0.5">
							{#each Array(4) as _, i}
								<div
									class="w-1 rounded-sm transition-all"
									style="
										height: {8 + i * 4}px;
										background: {i < signal.bars ? signal.color : 'var(--bg-hover)'};
										opacity: {i < signal.bars ? 1 : 0.4};
									"
								></div>
							{/each}
						</div>
						<span class="text-[10px] text-[var(--text-muted)] font-mono">{rssi} dBm</span>
					</div>
				{:else if battery && batteryPercent !== null}
					<div class="flex flex-col items-end gap-1" title="Battery: {battery.label} ({batteryPercent}%)">
						<div class="battery-icon" style="border-color: {battery.color};">
							<div class="battery-level" style="width: {batteryPercent}%; background: {battery.color};"></div>
						</div>
						<span class="text-[10px] font-mono" style="color: {battery.color};">{batteryPercent}%</span>
					</div>
				{/if}

				<!-- ML Confidence Badge -->
				{#if confidenceBadge}
					<div class="confidence-badge" title="ML confidence: {confidenceBadge.label} ({(confidence! * 100).toFixed(0)}%)">
						<span class="text-xs">{confidenceBadge.emoji}</span>
						<span class="text-[10px]" style="color: {confidenceBadge.color};">{confidenceBadge.label}</span>
					</div>
				{/if}

				<!-- Pairing status indicator -->
				{#if !isPaired}
					<div class="pairing-badge" title="Device not paired - readings not being logged">
						<svg class="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
							<path stroke-linecap="round" stroke-linejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
						</svg>
						Unpaired
					</div>
				{/if}
			</div>
		</div>

		<!-- Anomaly Alert Banner -->
		{#if isAnomaly && anomalyReasons.length > 0}
			<div class="anomaly-alert">
				<div class="flex items-start gap-2">
					<svg class="w-5 h-5 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
						<path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
					</svg>
					<div class="flex-1">
						<p class="font-semibold text-sm mb-1">Anomaly Detected</p>
						<ul class="text-xs space-y-0.5">
							{#each anomalyReasons as reason}
								<li>• {reason}</li>
							{/each}
						</ul>
					</div>
				</div>
			</div>
		{/if}

		<!-- Main readings grid -->
		<div class="grid grid-cols-2 gap-3 mb-4">
			<!-- Specific Gravity -->
			<div class="reading-box">
				<p class="reading-value">
					{formatSG(currentSg)}<span class="reading-unit">{gravityUnit !== 'SG' ? gravityUnit : ''}</span>
				</p>
				<p class="reading-label">
					{gravityUnit === 'SG' ? 'Gravity' : gravityUnit === '°P' ? 'Plato' : 'Brix'}
				</p>
			</div>

			<!-- Temperature -->
			<div class="reading-box">
				<p class="reading-value">
					{#if currentTemp !== null}
						{formatTempValue(currentTemp)}<span class="reading-unit">{tempUnit}</span>
					{:else}
						--<span class="reading-unit">{tempUnit}</span>
					{/if}
				</p>
				<p class="reading-label">
					Temp
				</p>
			</div>
		</div>

		<!-- Raw values (if calibrated) -->
		{#if (currentSg !== sgRaw || currentTemp !== tempRaw) && deviceReading}
			<div
				class="text-[11px] text-[var(--text-muted)] font-mono mb-3 px-1"
			>
				<span class="opacity-60">Raw:</span>
				<span class="ml-1">{formatSG(sgRaw)}</span>
				<span class="mx-1 opacity-40">·</span>
				<span>{tempRaw !== null ? formatTempValue(tempRaw) : '--'}{tempUnit}</span>
			</div>
		{/if}

		<!-- Expandable chart section - use CSS to hide instead of destroying -->
		<!-- Key on batch.id ensures stable component identity across parent re-renders -->
		{#if chartMounted}
			<div class="chart-section" class:hidden={!expanded}>
				{#key batch.id}
					<FermentationChart
						batchId={batch.id}
						deviceColor={deviceColor}
						originalGravity={batch.measured_og}
						controlEvents={controlEvents}
					/>
				{/key}
			</div>
		{/if}

		<!-- Footer -->
		<div class="flex justify-between items-center pt-3 border-t border-[var(--bg-hover)]">
			<span class="text-[11px] text-[var(--text-muted)]">Updated {lastSeenText}</span>
			<div class="flex items-center gap-2">
				<!-- View Details Link -->
				<a
					href="/batches/{batch.id}"
					class="view-details-link"
					aria-label="View batch details"
				>
					View Details
				</a>

				{#if onToggleExpand}
					<button
						type="button"
						class="expand-btn"
						onclick={onToggleExpand}
						aria-label={expanded ? 'Collapse chart' : 'Expand chart'}
					>
						<svg
							class="w-4 h-4 transition-transform"
							class:rotate-180={expanded}
							fill="none"
							viewBox="0 0 24 24"
							stroke="currentColor"
							stroke-width="2"
						>
							<path stroke-linecap="round" stroke-linejoin="round" d="M19 9l-7 7-7-7" />
						</svg>
					</button>
				{/if}
				<div class="live-indicator"></div>
			</div>
		</div>
	</div>
</div>

<style>
	.card {
		background: var(--bg-surface);
		border: 1px solid var(--border-subtle);
		border-radius: 0.5rem;
		overflow: hidden;
		transition: border-color var(--transition);
		animation: fadeIn 0.2s ease-out;
	}

	@keyframes fadeIn {
		from { opacity: 0; transform: translateY(4px); }
		to { opacity: 1; transform: translateY(0); }
	}

	.card:hover {
		border-color: var(--border-default);
	}

	/* Reading boxes */
	.reading-box {
		background: var(--bg-elevated);
		border-radius: 0.375rem;
		padding: 1rem;
		text-align: center;
	}

	.reading-value {
		font-size: 1.875rem;
		font-weight: 500;
		font-family: var(--font-mono);
		letter-spacing: -0.025em;
		color: var(--text-primary);
	}

	.reading-unit {
		font-size: 1.125rem;
		color: var(--text-secondary);
	}

	.reading-label {
		font-size: 0.6875rem;
		color: var(--text-muted);
		text-transform: uppercase;
		letter-spacing: 0.1em;
		margin-top: 0.25rem;
		font-weight: 500;
	}

	/* Live indicator dot */
	.live-indicator {
		width: 0.375rem;
		height: 0.375rem;
		border-radius: 50%;
		background: var(--positive);
	}

	.expanded {
		grid-column: span 2;
	}

	@media (max-width: 768px) {
		.expanded {
			grid-column: span 1;
		}
	}

	.wide {
		max-width: 28rem;
	}

	@media (min-width: 768px) {
		.wide {
			max-width: 36rem;
		}
	}

	/* When expanded with chart, allow full width */
	.wide.expanded {
		max-width: 56rem;
		width: 100%;
	}

	.wide .text-3xl {
		font-size: 2.5rem;
	}

	.chart-section {
		margin-top: 1rem;
		padding-top: 1rem;
		border-top: 1px solid var(--bg-hover);
	}

	.chart-section.hidden {
		display: none;
	}

	.view-details-link {
		display: inline-flex;
		align-items: center;
		padding: 0.375rem 0.75rem;
		font-size: 0.75rem;
		font-weight: 500;
		color: var(--text-secondary);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		border-radius: 0.375rem;
		text-decoration: none;
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.view-details-link:hover {
		color: var(--accent);
		border-color: var(--accent-muted);
		background: var(--accent-muted);
	}

	.expand-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 1.75rem;
		height: 1.75rem;
		border-radius: 0.375rem;
		color: var(--text-muted);
		background: var(--bg-elevated);
		border: 1px solid var(--bg-hover);
		cursor: pointer;
		transition: all 0.15s ease;
	}

	.expand-btn:hover {
		color: var(--accent);
		border-color: var(--accent-muted);
		background: var(--accent-muted);
	}

	/* Beer name editing */
	.beer-name-btn {
		display: flex;
		align-items: center;
		gap: 0.5rem;
		background: none;
		border: none;
		padding: 0;
		cursor: pointer;
		text-align: left;
		max-width: 100%;
	}

	.beer-name-btn:hover .edit-icon {
		opacity: 1;
	}

	.edit-icon {
		flex-shrink: 0;
		width: 0.875rem;
		height: 0.875rem;
		color: var(--text-muted);
		opacity: 0;
		transition: opacity 0.15s ease;
	}

	.beer-name-input {
		width: 100%;
		font-size: 1.125rem;
		font-weight: 600;
		color: var(--text-primary);
		background: var(--bg-elevated);
		border: 1px solid var(--accent);
		border-radius: 0.375rem;
		padding: 0.25rem 0.5rem;
		outline: none;
	}

	.beer-name-input:disabled {
		opacity: 0.6;
	}

	.beer-name-input.error {
		border-color: var(--negative);
	}

	.error-message {
		font-size: 0.75rem;
		color: var(--negative);
		margin-top: 0.25rem;
	}

	.pairing-badge {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.25rem 0.5rem;
		background: var(--warning-muted);
		color: var(--warning);
		border: 1px solid var(--warning);
		border-radius: 0.25rem;
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.025em;
	}

	.confidence-badge {
		display: flex;
		align-items: center;
		gap: 0.25rem;
		padding: 0.125rem 0.375rem;
		background: var(--bg-secondary);
		border: 1px solid var(--border);
		border-radius: 0.25rem;
		font-weight: 600;
	}

	.anomaly-alert {
		margin: 0 0 1rem 0;
		padding: 0.75rem;
		background: var(--warning-muted);
		border: 1px solid var(--warning);
		border-radius: 0.5rem;
		color: var(--warning);
	}

	.anomaly-alert svg {
		color: var(--warning);
	}

	.anomaly-alert ul {
		list-style: none;
		padding: 0;
		margin: 0;
	}

	/* Battery icon styles */
	.battery-icon {
		width: 24px;
		height: 12px;
		border: 1.5px solid;
		border-radius: 2px;
		padding: 1px;
		position: relative;
	}

	.battery-icon::after {
		content: '';
		position: absolute;
		right: -4px;
		top: 50%;
		transform: translateY(-50%);
		width: 2px;
		height: 6px;
		background: currentColor;
		border-radius: 0 1px 1px 0;
	}

	.battery-level {
		height: 100%;
		border-radius: 1px;
		transition: width 0.3s ease;
	}
</style>
