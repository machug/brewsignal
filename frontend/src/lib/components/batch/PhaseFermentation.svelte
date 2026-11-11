<script lang="ts">
	import type { BatchResponse, BatchProgressResponse, BatchControlStatus, ControlEvent } from '$lib/api';
	import type { TiltReading } from '$lib/stores/tilts.svelte';
	import { formatTemp, getTempUnit, configState } from '$lib/stores/config.svelte';
	import BatchFermentationCard from './BatchFermentationCard.svelte';
	import BatchRecipeTargetsCard from './BatchRecipeTargetsCard.svelte';
	import BatchAlertsCard from './BatchAlertsCard.svelte';
	import MLPredictions from './MLPredictions.svelte';
	import BatchNotesCard from './BatchNotesCard.svelte';
	import FermentationChart from '../FermentationChart.svelte';

	interface Props {
		batch: BatchResponse;
		progress: BatchProgressResponse | null;
		liveReading: TiltReading | null;
		controlStatus: BatchControlStatus | null;
		controlEvents: ControlEvent[];
		hasTempControl: boolean;
		heaterLoading: boolean;
		tempControlCollapsed: boolean;
		onOverride: (deviceType: 'heater' | 'cooler', state: 'on' | 'off' | null) => void;
		onClearOverrides: () => void;
		onTempControlToggle: () => void;
	}

	let {
		batch,
		progress,
		liveReading,
		controlStatus,
		controlEvents,
		hasTempControl,
		heaterLoading,
		tempControlCollapsed,
		onOverride,
		onClearOverrides,
		onTempControlToggle,
	}: Props = $props();

	let tempUnit = $derived(getTempUnit());

	function formatTempValue(value?: number | null): string {
		if (value === undefined || value === null) return '--';
		return formatTemp(value);
	}
</script>

<div class="content-grid">
	<!-- Left column -->
	<div class="stats-section">
		<!-- Fermentation Card (includes live readings) -->
		<BatchFermentationCard
			{batch}
			currentSg={liveReading?.sg ?? progress?.measured?.current_sg}
			{progress}
			{liveReading}
		/>

		<!-- Recipe Targets Card (only if recipe exists) -->
		{#if batch.recipe}
			<BatchRecipeTargetsCard recipe={batch.recipe} yeastStrain={batch.yeast_strain} />
		{/if}

		<!-- Notes Card (only if notes exist) -->
		{#if batch.notes}
			<BatchNotesCard notes={batch.notes} />
		{/if}
	</div>

	<!-- Right column -->
	<div class="info-section">
		<!-- Active Alerts Card (only show during fermentation/conditioning) -->
		{#if batch.status === 'fermenting' || batch.status === 'conditioning'}
			<BatchAlertsCard batchId={batch.id} />
		{/if}

		<!-- ML Predictions Panel -->
		<MLPredictions
			batchId={batch.id}
			batchStatus={batch.status}
			measuredOg={batch.measured_og}
			measuredFg={batch.measured_fg ?? progress?.measured?.current_sg}
			recipeFg={batch.recipe?.fg}
			currentSg={liveReading?.sg ?? progress?.measured?.current_sg}
			{liveReading}
		/>

		<!-- Temperature Control Card -->
		{#if hasTempControl && (batch.status === 'fermenting' || batch.status === 'conditioning')}
			<div class="info-card temp-control-card"
				class:heater-on={controlStatus?.heater_state === 'on'}
				class:cooler-on={controlStatus?.cooler_state === 'on'}
				class:collapsed={tempControlCollapsed}>
				<button
					type="button"
					class="collapsible-header"
					onclick={onTempControlToggle}
					aria-expanded={!tempControlCollapsed}
				>
					<h3 class="info-title">Temperature Control</h3>
					<div class="collapse-indicator">
						{#if controlStatus?.heater_state === 'on'}
							<span class="status-badge heater">Heating</span>
						{:else if controlStatus?.cooler_state === 'on'}
							<span class="status-badge cooler">Cooling</span>
						{:else if tempControlCollapsed && controlStatus}
							<span class="status-badge idle num">Target {formatTempValue(controlStatus.target_temp)}&thinsp;{tempUnit}</span>
						{/if}
						<svg class="chevron" class:rotated={!tempControlCollapsed} fill="none" viewBox="0 0 24 24" stroke="currentColor">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
						</svg>
					</div>
				</button>

				{#if !tempControlCollapsed}
				<!-- Device status indicators -->
				<div class="device-status-row">
					{#if batch.heater_entity_id}
						<div class="device-chip heater" class:active={controlStatus?.heater_state === 'on'} title={batch.heater_entity_id}>
							<span class="chip-icon" aria-hidden="true"></span>
							<span class="chip-label">Heater</span>
							<span class="chip-state">{controlStatus?.heater_state === 'on' ? 'ON' : 'OFF'}</span>
						</div>
					{/if}
					{#if batch.cooler_entity_id}
						<div class="device-chip cooler" class:active={controlStatus?.cooler_state === 'on'} title={batch.cooler_entity_id}>
							<span class="chip-icon" aria-hidden="true"></span>
							<span class="chip-label">Cooler</span>
							<span class="chip-state">{controlStatus?.cooler_state === 'on' ? 'ON' : 'OFF'}</span>
						</div>
					{/if}
				</div>

				{#if controlStatus}
					<div class="control-details">
						<div class="control-detail">
							<span class="detail-label">Target</span>
							<span class="detail-value">{formatTempValue(controlStatus.target_temp)}&thinsp;{tempUnit}</span>
						</div>
						<div class="control-detail">
							<span class="detail-label">Hysteresis</span>
							<span class="detail-value">&plusmn;{controlStatus.hysteresis?.toFixed(1) || '--'}&thinsp;{tempUnit}</span>
						</div>
					</div>

					{#if controlStatus.override_active}
						<div class="override-banner">
							<span>Override active: {controlStatus.override_state?.toUpperCase()}</span>
							<button
								type="button"
								class="override-cancel-inline"
								onclick={() => onClearOverrides()}
								disabled={heaterLoading}
							>
								Cancel
							</button>
						</div>
					{/if}

					<div class="override-controls">
						<span class="override-label">Manual Override (1hr)</span>
						<div class="override-btns-grid">
							{#if batch.heater_entity_id}
								<button
									type="button"
									class="override-btn heat-on"
									onclick={() => onOverride('heater', 'on')}
									disabled={heaterLoading}
								>
									Force Heat ON
								</button>
								<button
									type="button"
									class="override-btn heat-off"
									onclick={() => onOverride('heater', 'off')}
									disabled={heaterLoading}
								>
									Force Heat OFF
								</button>
							{/if}

							{#if batch.cooler_entity_id}
								<button
									type="button"
									class="override-btn cool-on"
									onclick={() => onOverride('cooler', 'on')}
									disabled={heaterLoading}
								>
									Force Cool ON
								</button>
								<button
									type="button"
									class="override-btn cool-off"
									onclick={() => onOverride('cooler', 'off')}
									disabled={heaterLoading}
								>
									Force Cool OFF
								</button>
							{/if}

							<button
								type="button"
								class="override-btn auto-mode"
								onclick={() => onClearOverrides()}
								disabled={heaterLoading}
							>
								Auto Mode
							</button>
						</div>
					</div>
				{/if}
				{/if}
			</div>
		{:else if (batch.heater_entity_id || batch.cooler_entity_id) && batch.status !== 'fermenting'}
			<div class="info-card">
				<h3 class="info-title">Temperature Control</h3>
				<div class="no-device">
					{#if batch.heater_entity_id}
						<span>Heater: {batch.heater_entity_id}</span>
					{/if}
					{#if batch.cooler_entity_id}
						<span>Cooler: {batch.cooler_entity_id}</span>
					{/if}
					<span class="hint">Active only during fermentation</span>
				</div>
			</div>
		{/if}

	</div>
</div>

<!-- Fermentation Chart (shows historical data for all batches with a device) -->
{#if batch.device_id}
	<div class="chart-section">
		<FermentationChart
			batchId={batch.id}
			deviceColor={batch.device_id}
			originalGravity={batch.measured_og}
			{controlEvents}
		/>
	</div>
{/if}

<style>
	.num,
	.detail-value,
	.chip-state {
		font-family: var(--font-num);
		font-variant-numeric: tabular-nums lining-nums;
	}

	/* Content grid: primary instrument column + secondary column */
	.content-grid {
		display: grid;
		grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
		gap: var(--space-lg);
		align-items: start;
	}
	@media (max-width: 900px) {
		.content-grid {
			grid-template-columns: minmax(0, 1fr);
		}
	}
	.stats-section,
	.info-section {
		display: flex;
		flex-direction: column;
		gap: var(--space-md);
		min-width: 0;
	}

	/* Section: hairline top rule, no floating card */
	.info-card {
		border-top: 1px solid var(--rule-strong);
		padding-top: var(--space-sm);
	}
	.info-title {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		color: var(--ink-muted);
		text-transform: uppercase;
		letter-spacing: 0.08em;
		margin: 0 0 var(--space-sm) 0;
	}
	.chart-section {
		margin-top: var(--space-lg);
	}
	.no-device {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
		font-size: var(--text-sm);
		color: var(--ink-secondary);
	}
	.hint {
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}

	/* Temperature control */
	.collapsible-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		width: 100%;
		min-height: 44px;
		padding: 0;
		margin-bottom: var(--space-xs);
		cursor: pointer;
		text-align: left;
	}
	.temp-control-card.collapsed .collapsible-header {
		margin-bottom: 0;
	}
	.collapsible-header .info-title {
		margin: 0;
	}
	.collapse-indicator {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
	}
	.status-badge {
		font-family: var(--font-display);
		font-size: 0.6875rem;
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.06em;
		padding: 2px 7px;
		border-radius: 2px;
		border: 1px solid var(--rule-strong);
		color: var(--ink-secondary);
	}
	.status-badge.heater {
		border-color: color-mix(in oklch, var(--status-warn) 55%, transparent);
		color: var(--status-warn);
	}
	.status-badge.cooler {
		border-color: color-mix(in oklch, var(--temp-trace) 55%, transparent);
		color: var(--temp-trace);
	}
	.chevron {
		width: 1rem;
		height: 1rem;
		color: var(--ink-muted);
		transition: transform 150ms var(--ease-out-quart);
	}
	.chevron.rotated {
		transform: rotate(180deg);
	}

	.device-status-row {
		display: flex;
		gap: var(--space-xs);
		margin-bottom: var(--space-sm);
	}
	.device-chip {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		flex: 1;
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid var(--rule-hairline);
		border-radius: 2px;
		font-size: var(--text-xs);
		color: var(--ink-muted);
	}
	.chip-icon {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		border: 1px solid var(--rule-strong);
		flex-shrink: 0;
	}
	.device-chip.active .chip-icon {
		background: currentColor;
		border-color: currentColor;
	}
	.chip-label {
		font-weight: 700;
		color: var(--ink-secondary);
	}
	.chip-state {
		margin-left: auto;
		font-weight: 600;
		font-size: 0.6875rem;
	}
	.device-chip.heater.active {
		border-color: color-mix(in oklch, var(--status-warn) 55%, transparent);
		color: var(--status-warn);
	}
	.device-chip.cooler.active {
		border-color: color-mix(in oklch, var(--temp-trace) 55%, transparent);
		color: var(--temp-trace);
	}

	/* Target / hysteresis readout */
	.control-details {
		display: grid;
		grid-template-columns: 1fr 1fr;
		margin-bottom: var(--space-sm);
		border-top: 1px solid var(--rule-hairline);
		border-bottom: 1px solid var(--rule-hairline);
	}
	.control-detail {
		display: flex;
		flex-direction: column;
		gap: var(--space-2xs);
		padding: var(--space-xs) var(--space-sm);
	}
	.control-detail + .control-detail {
		border-left: 1px solid var(--rule-hairline);
	}
	.detail-label,
	.override-label {
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		text-transform: uppercase;
		letter-spacing: 0.07em;
		color: var(--ink-muted);
	}
	.detail-value {
		font-size: var(--text-base);
		font-weight: 600;
		color: var(--ink-primary);
	}

	.override-banner {
		display: flex;
		align-items: center;
		gap: var(--space-xs);
		margin-bottom: var(--space-sm);
		padding: var(--space-xs) var(--space-sm);
		border: 1px solid color-mix(in oklch, var(--temp-trace) 50%, transparent);
		font-size: var(--text-xs);
		color: var(--temp-trace);
	}
	.override-cancel-inline {
		margin-left: auto;
		min-height: 32px;
		padding: 0 var(--space-xs);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		border-radius: 3px;
		border: 1px solid currentColor;
		color: var(--temp-trace);
		cursor: pointer;
	}
	.override-cancel-inline:hover:not(:disabled) {
		background: var(--bg-subtle);
	}
	.override-cancel-inline:disabled,
	.override-btn:disabled {
		opacity: 0.5;
		cursor: not-allowed;
	}

	.override-controls {
		display: flex;
		flex-direction: column;
		gap: var(--space-xs);
	}
	.override-btns-grid {
		display: grid;
		grid-template-columns: repeat(2, 1fr);
		gap: var(--space-xs);
	}
	.override-btn {
		min-height: 44px;
		padding: 0 var(--space-sm);
		font-family: var(--font-display);
		font-size: var(--text-xs);
		font-weight: 600;
		border-radius: 4px;
		background: var(--bg-surface);
		border: 1px solid var(--rule-strong);
		color: var(--ink-primary);
		cursor: pointer;
		transition: background-color 140ms var(--ease-out-quart);
	}
	.override-btn:hover:not(:disabled) {
		background: var(--bg-subtle);
	}
	.override-btn.heat-on:hover:not(:disabled),
	.override-btn.heat-off:hover:not(:disabled) {
		border-color: var(--status-warn);
	}
	.override-btn.cool-on:hover:not(:disabled),
	.override-btn.cool-off:hover:not(:disabled) {
		border-color: var(--temp-trace);
	}
	.override-btn.auto-mode {
		grid-column: 1 / -1;
		background: var(--accent-tint);
		border-color: var(--accent-rule);
		color: var(--accent);
	}
	.override-btn.auto-mode:hover:not(:disabled) {
		background: var(--accent-tint);
		border-color: var(--accent);
	}
</style>
